"""Study Assistant - 主应用入口"""
import logging
import sys
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# 确保项目根目录在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.core.config import get_config
from backend.core.database import init_database, engine
from backend.core.exceptions import StudyAssistantException
from backend.api.routes import projects, learning, qa, feynman, logs

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Study Assistant...")
    init_database()
    logger.info("Database initialized")

    from backend.core.scheduler import init_scheduler
    scheduler = init_scheduler()

    yield

    scheduler.shutdown()
    logger.info("Shutting down Study Assistant...")


app = FastAPI(
    title="Study Assistant API",
    description="基于多智能体架构的学习辅助工具",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=os.path.join(frontend_dir, "static")), name="static")


# API 路由
app.include_router(projects.router, prefix="/api/v1/projects", tags=["项目管理"])
app.include_router(learning.router, prefix="/api/v1/learning", tags=["学习流程"])
app.include_router(qa.router, prefix="/api/v1/qa", tags=["问答"])
app.include_router(feynman.router, prefix="/api/v1/feynman", tags=["费曼学习"])
app.include_router(logs.router, prefix="/api/v1/logs", tags=["学习日志"])


@app.get("/")
async def index():
    frontend_index = os.path.join(frontend_dir, "index.html")
    if os.path.exists(frontend_index):
        return FileResponse(frontend_index)
    return {"message": "Study Assistant API", "docs": "/docs"}


@app.get("/health")
async def health():
    return {"status": "healthy", "service": "Study Assistant", "version": "1.0.0"}


@app.exception_handler(StudyAssistantException)
async def app_exception_handler(request: Request, exc: StudyAssistantException):
    return JSONResponse(status_code=exc.status_code, content={"error": exc.error_code, "message": exc.message})


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    config = get_config()
    return JSONResponse(
        status_code=500,
        content={"error": "INTERNAL_ERROR", "message": str(exc) if config.debug else "服务器内部错误"},
    )


@app.middleware("http")
async def log_requests(request: Request, call_next):
    import time
    start = time.time()
    response = await call_next(request)
    elapsed = time.time() - start
    logger.info(f"{request.method} {request.url.path} -> {response.status_code} ({elapsed:.3f}s)")
    return response
