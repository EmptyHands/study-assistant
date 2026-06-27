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
            "project_id": project_id, "source_type": source_type,
            "source_path": source_path, "raw_content": "",
            "is_learnable": False, "learnability_reason": "",
            "content_type": "", "title": project.name,
            "framework": {}, "explanation": {}, "error": "",
        }
        from backend.core.progress import set_progress
        set_progress(project_id, "parsing", 10)
        result = await run_learning_pipeline(state)
        set_progress(project_id, "done", 100)
        return {"success": True, "result": result}
    except Exception as e:
        logger.error(f"学习流程失败: {e}")
        project2 = db.query(Project).filter(Project.id == project_id).first()
        if project2:
            project2.status = "pending"
            project2.learnability_reason = str(e)
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
            return {}
        return {
            "id": content.id, "title": content.title,
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
        content = db.query(LearningContent).filter(LearningContent.project_id == project_id).first()
        return {
            "project_id": project_id, "status": project.status,
            "has_content": content is not None,
        }
    finally:
        db.close()


async def update_learning_content(project_id: str) -> dict:
    """补充更新学习内容"""
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise NotFoundException(f"项目不存在: {project_id}")
        content = db.query(LearningContent).filter(LearningContent.project_id == project_id).first()
        if not content or not content.raw_content:
            return {"needs_update": False, "supplements_count": 0, "reason": "No original content to supplement from"}
        from backend.agents.log_agent import LogAgent
        agent = LogAgent()
        existing = content.sq3r_json or {}
        result = await agent.supplement_content(existing, content.raw_content)
        if result.get("needs_update") and result.get("supplements"):
            existing["supplements"] = (existing.get("supplements") or []) + result["supplements"]
            content.sq3r_json = existing
            db.commit()
            return {"needs_update": True, "supplements_count": len(result["supplements"]), "reason": result.get("reason", "")}
        return {"needs_update": False, "supplements_count": 0, "reason": result.get("reason", "Content is up to date")}
    finally:
        db.close()


def get_pipeline_progress(project_id: str) -> dict:
    """Get learning pipeline progress"""
    from backend.core.progress import get_progress
    return get_progress(project_id)
