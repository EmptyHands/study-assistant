"""问答 API 路由"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from backend.services.qa_service import ask_question, get_qa_history

router = APIRouter()

class AskRequest(BaseModel):
    question: str

@router.post("/{project_id}/ask")
async def ask(project_id: str, req: AskRequest):
    try:
        result = await ask_question(project_id, req.question)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/{project_id}/history")
async def history(project_id: str, limit: int = 50):
    try:
        records = get_qa_history(project_id, limit)
        return {"records": records}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
