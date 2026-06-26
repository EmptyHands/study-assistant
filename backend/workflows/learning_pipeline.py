"""LangGraph 学习流程 Pipeline"""
import logging
from typing import Literal
from langgraph.graph import StateGraph, END
from .states import LearningState

logger = logging.getLogger(__name__)


async def parse_content(state: LearningState) -> dict:
    """Step 0: 解析输入内容"""
    from backend.utils.file_parser import parse_file, parse_directory
    from backend.utils.git_handler import clone_repo
    import os

    source_type = state.get("source_type", "file")
    source_path = state.get("source_path", "")

    if source_type == "concept":
        return {"raw_content": source_path, "title": source_path[:100]}

    if source_type == "git":
        result = clone_repo(source_path)
        if not result["success"]:
            return {"error": result["error"], "is_learnable": False, "learnability_reason": result["error"]}
        dir_result = parse_directory(result["path"])
        return {"raw_content": dir_result.get("text", ""), "source_path": result["path"]}

    # file type
    if os.path.isdir(source_path):
        result = parse_directory(source_path)
        return {"raw_content": result.get("text", ""),
                "title": os.path.basename(source_path.rstrip("/\\"))}
    else:
        result = parse_file(source_path)
        return {"raw_content": result.get("text", ""),
                "title": os.path.basename(source_path)}


async def learnability_check(state: LearningState) -> dict:
    """Step 1: 判断可学性"""
    from backend.agents.learnability_agent import LearnabilityAgent
    agent = LearnabilityAgent()
    result = await agent.run({
        "raw_content": state.get("raw_content", ""),
        "source_type": state.get("source_type", "file"),
    })
    return {
        "is_learnable": result["is_learnable"],
        "learnability_reason": result["reason"],
        "content_type": result["content_type"],
        "title": result["title"] or state.get("title", ""),
    }


def route_after_check(state: LearningState) -> Literal["framework_analysis", "end_not_learnable"]:
    if state.get("is_learnable", False):
        return "framework_analysis"
    return "end_not_learnable"


async def framework_analysis(state: LearningState) -> dict:
    """Step 2: 框架分析"""
    from backend.agents.framework_agent import FrameworkAgent
    agent = FrameworkAgent()
    result = await agent.run({
        "raw_content": state.get("raw_content", ""),
        "content_type": state.get("content_type", ""),
        "title": state.get("title", ""),
    })
    return {"framework": result.get("framework", {})}


async def content_explanation(state: LearningState) -> dict:
    """Step 3: 内容讲解"""
    from backend.agents.explanation_agent import ExplanationAgent
    agent = ExplanationAgent()
    result = await agent.run({
        "raw_content": state.get("raw_content", ""),
        "framework": state.get("framework", {}),
    })
    return {"explanation": result.get("explanation", {}),
            "title": result.get("title") or state.get("title", "")}


async def save_learning_content(state: LearningState) -> dict:
    """Step 4: 保存学习内容到数据库和向量库"""
    from backend.core.database import get_db_session
    from backend.models.database import Project, LearningContent
    from backend.core.vector_store import get_vector_store
    import json

    db = get_db_session()
    try:
        # 更新项目状态
        project = db.query(Project).filter(Project.id == state["project_id"]).first()
        if project:
            project.status = "ready"
            project.name = state.get("title", project.name)

        # 保存或更新学习内容
        content = db.query(LearningContent).filter(
            LearningContent.project_id == state["project_id"]
        ).first()
        if content:
            content.title = state.get("title", "")
            content.framework_json = state.get("framework", {})
            content.explanation_md = json.dumps(state.get("explanation", {}), ensure_ascii=False)
            content.sq3r_json = state.get("explanation", {})
            content.raw_content = state.get("raw_content", "")
        else:
            content = LearningContent(
                project_id=state["project_id"],
                title=state.get("title", ""),
                framework_json=state.get("framework", {}),
                explanation_md=json.dumps(state.get("explanation", {}), ensure_ascii=False),
                sq3r_json=state.get("explanation", {}),
                raw_content=state.get("raw_content", ""),
            )
            db.add(content)
        db.commit()

        # 向量化存储
        raw = state.get("raw_content", "")
        chunks = _chunk_text(raw, chunk_size=1000, overlap=200)
        try:
            vs = get_vector_store()
            await vs.add_documents(state["project_id"], chunks)
        except Exception as e:
            logger.warning(f"向量存储失败（非致命）: {e}")

    except Exception as e:
        logger.error(f"保存学习内容失败: {e}")
        return {"error": str(e)}
    finally:
        db.close()

    return {}


def _chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """将长文本切分为重叠的块"""
    if not text:
        return []
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return chunks


async def end_not_learnable(state: LearningState) -> dict:
    """不可学习时的结束节点"""
    from backend.core.database import get_db_session
    from backend.models.database import Project

    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == state["project_id"]).first()
        if project:
            project.status = "not_learnable"
            project.learnability_reason = state.get("learnability_reason", "")
            db.commit()
    finally:
        db.close()
    return {}


def build_learning_pipeline() -> StateGraph:
    """构建主学习 Pipeline"""
    workflow = StateGraph(LearningState)

    workflow.add_node("parse_content", parse_content)
    workflow.add_node("learnability_check", learnability_check)
    workflow.add_node("framework_analysis", framework_analysis)
    workflow.add_node("content_explanation", content_explanation)
    workflow.add_node("save_content", save_learning_content)
    workflow.add_node("end_not_learnable", end_not_learnable)

    workflow.set_entry_point("parse_content")
    workflow.add_edge("parse_content", "learnability_check")
    workflow.add_conditional_edges("learnability_check", route_after_check, {
        "framework_analysis": "framework_analysis",
        "end_not_learnable": "end_not_learnable",
    })
    workflow.add_edge("framework_analysis", "content_explanation")
    workflow.add_edge("content_explanation", "save_content")
    workflow.add_edge("save_content", END)
    workflow.add_edge("end_not_learnable", END)

    return workflow.compile()


async def run_learning_pipeline(state: LearningState):
    """执行学习流程"""
    pipeline = build_learning_pipeline()
    result = await pipeline.ainvoke(state)
    return result
