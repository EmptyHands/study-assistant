"""学习内容 API 路由"""
from fastapi import APIRouter, HTTPException
from backend.services.learning_service import (
    start_learning, get_learning_content, get_project_status, update_learning_content,
)

router = APIRouter()


@router.post("/{project_id}/start")
async def start_learning_pipeline(project_id: str):
    """启动学习流程"""
    from backend.services.project_service import get_project
    try:
        project = get_project(project_id)
        result = await start_learning(project_id, project["source_type"], project["source_path"])
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}/status")
async def check_status(project_id: str):
    """获取学习状态"""
    try:
        return get_project_status(project_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{project_id}/content")
async def get_content(project_id: str):
    """获取 SQ3R 学习内容"""
    try:
        content = get_learning_content(project_id)
        return {"content": content}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/{project_id}/update")
async def update_content(project_id: str):
    """补充更新学习内容"""
    try:
        result = await update_learning_content(project_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
