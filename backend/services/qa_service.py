"""问答服务"""
import logging
from backend.core.database import get_db_session
from backend.models.database import Project, QARecord, LearningContent
from backend.core.exceptions import NotFoundException
from backend.agents.qa_agent import QAAgent

logger = logging.getLogger(__name__)


async def ask_question(project_id: str, question: str) -> dict:
    """处理问答请求"""
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise NotFoundException(f"项目不存在: {project_id}")

        content = db.query(LearningContent).filter(LearningContent.project_id == project_id).first()
        summary = ""
        raw_content = ""
        if content:
            import json
            summary = json.dumps(content.sq3r_json or {}, ensure_ascii=False)
            raw_content = content.raw_content or ""

        # B1: 获取最近 QA 历史，供 Agent 理解多轮对话上下文
        recent_qa = (
            db.query(QARecord)
            .filter(QARecord.project_id == project_id)
            .order_by(QARecord.created_at.desc())
            .limit(5)
            .all()
        )
        history = [
            {"question": r.question, "answer": r.answer[:300]}
            for r in reversed(recent_qa)
        ]

        agent = QAAgent()
        result = await agent.run({
            "question": question,
            "project_id": project_id,
            "summary": summary,
            "raw_content": raw_content,
            "history": history,
        })

        # 保存问答记录
        record = QARecord(
            project_id=project_id,
            question=question,
            answer=result["answer"],
            source_type=result.get("source_type", "summary"),
        )
        db.add(record)
        db.commit()

        return {
            "question": question,
            "answer": result["answer"],
            "source_type": result.get("source_type", "summary"),
            "id": record.id,
        }
    finally:
        db.close()


def get_qa_history(project_id: str, limit: int = 50) -> list[dict]:
    """获取问答历史"""
    db = get_db_session()
    try:
        records = (
            db.query(QARecord)
            .filter(QARecord.project_id == project_id)
            .order_by(QARecord.created_at.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": r.id,
                "question": r.question,
                "answer": r.answer,
                "source_type": r.source_type,
                "created_at": str(r.created_at) if r.created_at else None,
            }
            for r in reversed(records)
        ]
    finally:
        db.close()


async def stream_answer(project_id: str, question: str):
    """流式回答 - 逐token返回"""
    from backend.agents.qa_agent import QAAgent
    from backend.core.database import get_db_session
    from backend.models.database import LearningContent
    import json
    
    db = get_db_session()
    try:
        content = db.query(LearningContent).filter(LearningContent.project_id == project_id).first()
        summary = json.dumps(content.sq3r_json, ensure_ascii=False)[:3000] if content and content.sq3r_json else ""
    finally:
        db.close()
    
    agent = QAAgent()
    async for token in agent.stream_answer(
        question=question,
        summary=summary,
        project_id=project_id,
    ):
        yield token
