"""项目服务"""
import logging
import os
import shutil
from datetime import datetime
from backend.core.database import get_db_session
from backend.models.database import Project, LearningContent
from backend.core.exceptions import NotFoundException, ValidationException

logger = logging.getLogger(__name__)

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "data", "projects")


def _ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)


def create_project(name: str, source_type: str, source_path: str = None) -> dict:
    """创建新项目"""
    db = get_db_session()
    try:
        project = Project(name=name, source_type=source_type, source_path=source_path, status="pending")
        db.add(project)
        db.commit()
        db.refresh(project)
        return _project_to_dict(project)
    finally:
        db.close()


def get_project(project_id: str) -> dict:
    """获取项目详情"""
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise NotFoundException(f"项目不存在: {project_id}")
        return _project_to_dict(project)
    finally:
        db.close()


def list_projects() -> list[dict]:
    """列出所有项目"""
    db = get_db_session()
    try:
        projects = db.query(Project).order_by(Project.updated_at.desc()).all()
        return [_project_to_dict(p) for p in projects]
    finally:
        db.close()


def update_project(project_id: str, name: str = None) -> dict:
    """更新项目"""
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise NotFoundException(f"项目不存在: {project_id}")
        if name:
            project.name = name
        project.updated_at = datetime.utcnow()
        db.commit()
        db.refresh(project)
        return _project_to_dict(project)
    finally:
        db.close()


def delete_project(project_id: str) -> bool:
    """删除项目及相关数据"""
    from backend.core.vector_store import get_vector_store

    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise NotFoundException(f"项目不存在: {project_id}")

        # 清理上传的文件
        if project.source_path and os.path.exists(project.source_path) and UPLOAD_DIR in project.source_path:
            if os.path.isdir(project.source_path):
                shutil.rmtree(project.source_path, ignore_errors=True)
            else:
                os.remove(project.source_path)

        db.delete(project)
        db.commit()

        # 清理向量数据
        try:
            vs = get_vector_store()
            import asyncio
            asyncio.create_task(vs.delete_project(project_id))
        except Exception:
            pass

        # 清理父子块存储
        try:
            from backend.core.document_store import get_document_store
            get_document_store().purge(project_id)
        except Exception:
            pass

        return True
    finally:
        db.close()


def save_uploaded_file(file_content: bytes, filename: str) -> str:
    """保存上传的文件，返回文件路径"""
    _ensure_upload_dir()
    safe_name = f"{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}_{filename}"
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, "wb") as f:
        f.write(file_content)
    return file_path


def get_project_with_content(project_id: str) -> dict:
    """获取项目及其学习内容"""
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise NotFoundException(f"项目不存在: {project_id}")
        result = _project_to_dict(project)
        if project.learning_content:
            result["learning_content"] = {
                "id": project.learning_content.id,
                "title": project.learning_content.title,
                "framework": project.learning_content.framework_json,
                "sq3r": project.learning_content.sq3r_json,
                "created_at": str(project.learning_content.created_at),
                "updated_at": str(project.learning_content.updated_at),
            }
        return result
    finally:
        db.close()


def purge_project_storage(project_id: str) -> dict:
    """手动清除项目存储（内部测试用）。不影响项目记录本身。"""
    from backend.core.document_store import get_document_store

    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise NotFoundException(f"项目不存在: {project_id}")
    finally:
        db.close()

    store = get_document_store()
    store.purge(project_id)
    return {"project_id": project_id, "purged": True}


def _project_to_dict(p: Project) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "source_type": p.source_type,
        "source_path": p.source_path,
        "status": p.status,
        "learnability_reason": p.learnability_reason,
        "created_at": str(p.created_at) if p.created_at else None,
        "updated_at": str(p.updated_at) if p.updated_at else None,
    }
