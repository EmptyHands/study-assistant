"""项目管理 API 路由"""
import os
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel
from typing import Optional
from backend.services.project_service import (
    create_project, get_project, list_projects, update_project,
    delete_project, save_uploaded_file, get_project_with_content,
)
from backend.utils.git_handler import get_repo_name

router = APIRouter()


class GitImportRequest(BaseModel):
    git_url: str
    name: Optional[str] = None


class ConceptImportRequest(BaseModel):
    concept: str
    name: Optional[str] = None


class RenameRequest(BaseModel):
    name: str


@router.post("/import/file")
async def import_file(file: UploadFile = File(...), name: str = Form(None)):
    """导入本地文件或文件夹（zip）"""
    try:
        content = await file.read()
        file_path = save_uploaded_file(content, file.filename or "upload")
        project_name = name or file.filename or "未命名项目"
        project = create_project(project_name, "file", file_path)
        return {"success": True, "project": project}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import/git")
async def import_git(req: GitImportRequest):
    """导入 Git 项目"""
    if not req.git_url.strip():
        raise HTTPException(status_code=400, detail="Git URL 不能为空")
    project_name = req.name or get_repo_name(req.git_url)
    project = create_project(project_name, "git", req.git_url.strip())
    return {"success": True, "project": project}


@router.post("/import/concept")
async def import_concept(req: ConceptImportRequest):
    """导入概念"""
    if not req.concept.strip():
        raise HTTPException(status_code=400, detail="概念不能为空")
    project_name = req.name or req.concept[:50]
    project = create_project(project_name, "concept", req.concept.strip())
    return {"success": True, "project": project}


@router.get("")
async def list_all_projects():
    """获取所有项目列表"""
    projects = list_projects()
    return {"projects": projects}


@router.get("/{project_id}")
async def get_project_detail(project_id: str):
    """获取项目详情"""
    try:
        project = get_project_with_content(project_id)
        return {"project": project}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{project_id}")
async def rename_project(project_id: str, req: RenameRequest):
    """重命名项目"""
    try:
        project = update_project(project_id, name=req.name)
        return {"success": True, "project": project}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.delete("/{project_id}")
async def remove_project(project_id: str):
    """删除项目"""
    try:
        delete_project(project_id)
        return {"success": True}
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))
