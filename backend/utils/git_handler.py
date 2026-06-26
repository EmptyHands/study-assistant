"""Git 仓库处理工具"""
import logging
import os
import tempfile
import shutil
from typing import Optional

logger = logging.getLogger(__name__)

# 常见的非学习型仓库特征
NON_LEARNING_REPO_PATTERNS = [
    "awesome-", "awesome_", ".github.io", "dotfiles", "cheatsheets",
    "interview", "resources", "roadmap", "best-websites", "tools",
]


def clone_repo(git_url: str, target_dir: Optional[str] = None) -> dict:
    """克隆 Git 仓库到本地"""
    try:
        from git import Repo, GitCommandError
    except ImportError:
        return {"success": False, "error": "gitpython 未安装，请运行: pip install gitpython"}

    if not target_dir:
        target_dir = tempfile.mkdtemp(prefix="study_repo_")

    try:
        logger.info(f"克隆仓库: {git_url} -> {target_dir}")
        Repo.clone_from(git_url, target_dir, depth=1)
        return {"success": True, "path": target_dir, "url": git_url}
    except GitCommandError as e:
        logger.error(f"Git clone failed: {e}")
        return {"success": False, "error": f"Git 克隆失败: {e}"}


def get_repo_name(git_url: str) -> str:
    """从 Git URL 提取仓库名"""
    url = git_url.rstrip("/").rstrip(".git")
    name = url.split("/")[-1]
    return name


def is_likely_learning_repo(git_url: str) -> tuple:
    """初步判断 Git URL 是否可能是学习型仓库"""
    url_lower = git_url.lower()
    for pattern in NON_LEARNING_REPO_PATTERNS:
        if pattern in url_lower:
            return False, f"该仓库可能是资源汇总型仓库（匹配模式: {pattern}），不推荐作为学习项目"
    return True, ""


def cleanup_clone(path: str):
    """清理克隆的临时目录"""
    try:
        if os.path.exists(path):
            shutil.rmtree(path, ignore_errors=True)
    except Exception as e:
        logger.warning(f"清理临时目录失败: {e}")
