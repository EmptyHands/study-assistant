"""学习服务"""
import logging
import json
from backend.core.database import get_db_session
from backend.models.database import Project, LearningContent
from backend.core.exceptions import NotFoundException
from backend.workflows.learning_pipeline import run_learning_pipeline

logger = logging.getLogger(__name__)


async def start_learning(project_id: str, source_type: str, source_path: str) -> dict:
    """启动学习流程"""
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise NotFoundException(f"项目不存在: {project_id}")

        project.status = "processing"
        db.commit()

        state = {
            "project_id": project_id,
            "source_type": source_type,
            "source_path": source_path,
            "raw_content": "",
            "is_learnable": False,
            "learnability_reason": "",
            "content_type": "",
            "title": project.name,
            "framework": {},
            "explanation": {},
            "error": "",
        }

        result = await run_learning_pipeline(state)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"学习流程失败: {e}")
        project = db.query(Project).filter(Project.id == project_id).first()
        if project:
            project.status = "pending"
            project.learnability_reason = str(e)
            db.commit()
        raise
    finally:
        db.close()


def get_learning_content(project_id: str) -> dict:
    """获取 SQ3R 学习内容"""
    db = get_db_session()
    try:
        content = db.query(LearningContent).filter(LearningContent.project_id == project_id).first()
        if not content:
            raise NotFoundException("学习内容尚未生成")
        return {
            "id": content.id,
            "project_id": content.project_id,
            "title": content.title,
            "framework": content.framework_json,
            "sq3r": content.sq3r_json,
            "created_at": str(content.created_at) if content.created_at else None,
            "updated_at": str(content.updated_at) if content.updated_at else None,
        }
    finally:
        db.close()


def get_project_status(project_id: str) -> dict:
    """获取项目学习状态"""
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise NotFoundException(f"项目不存在: {project_id}")
        has_content = project.learning_content is not None
        return {
            "project_id": project_id,
            "status": project.status,
            "has_content": has_content,
            "learnability_reason": project.learnability_reason,
        }
    finally:
        db.close()


async def update_learning_content(project_id: str) -> dict:
    """补充更新学习内容"""
    from backend.agents.log_agent import LogAgent

    db = get_db_session()
    try:
        content = db.query(LearningContent).filter(LearningContent.project_id == project_id).first()
        if not content:
            raise NotFoundException("学习内容尚未生成，请先启动学习")

        agent = LogAgent()
        existing = {
            "title": content.title,
            "framework": content.framework_json,
            "sq3r": content.sq3r_json,
        }
        result = await agent.supplement_content(existing, content.raw_content or "")

        if result.get("needs_update") and result.get("supplements"):
            sq3r = content.sq3r_json or {}
            for supplement in result["supplements"]:
                section = supplement.get("section", "")
                supplement_content = supplement.get("content", "")
                if "supplements" not in sq3r:
                    sq3r["supplements"] = []
                sq3r["supplements"].append({"section": section, "content": supplement_content, "added_at": str(__import__("datetime").datetime.utcnow())})
            content.sq3r_json = sq3r
            db.commit()

        return {
            "needs_update": result.get("needs_update", False),
            "supplements_count": len(result.get("supplements", [])),
            "reason": result.get("reason", ""),
        }
    finally:
        db.close()
