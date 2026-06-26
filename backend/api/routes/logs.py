"""学习日志 API 路由"""
from fastapi import APIRouter, HTTPException
from backend.services.log_service import (
    generate_daily_log, get_project_logs, get_latest_log, check_update_needed,
)

router = APIRouter()


@router.post("/{project_id}/generate")
async def generate_log(project_id: str):
    """生成今日学习日志"""
    try:
        result = await generate_daily_log(project_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{project_id}")
async def list_logs(project_id: str, limit: int = 30):
    """获取学习日志列表"""
    try:
        logs = get_project_logs(project_id, limit)
        return {"logs": logs}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{project_id}/latest")
async def latest_log(project_id: str):
    """获取最新学习摘要"""
    try:
        result = get_latest_log(project_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{project_id}/check-update")
async def check_update(project_id: str):
    """检查是否需要更新"""
    try:
        result = check_update_needed(project_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
