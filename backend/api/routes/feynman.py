"""费曼学习法 API 路由"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.feynman_service import start_feynman_session, submit_answer

router = APIRouter()


class AnswerRequest(BaseModel):
    session_id: str
    answer: str = ""
    confused: bool = False


@router.post("/{project_id}/start")
async def start_session(project_id: str):
    """开始费曼会话"""
    try:
        result = await start_feynman_session(project_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/answer")
async def answer(project_id: str, req: AnswerRequest):
    """提交回答"""
    try:
        result = await submit_answer(req.session_id, req.answer, req.confused)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{project_id}/confused")
async def confused(project_id: str, req: AnswerRequest):
    """用户表示不清楚"""
    try:
        result = await submit_answer(req.session_id, "我不太清楚", confused=True)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
