"""In-memory pipeline progress tracker (no deps to avoid circular imports)"""
_pipeline_progress = {}

def set_progress(project_id: str, stage: str, progress: int):
    _pipeline_progress[project_id] = {"stage": stage, "progress": progress}

def get_progress(project_id: str) -> dict:
    return _pipeline_progress.get(project_id, {"stage": "unknown", "progress": 0})
