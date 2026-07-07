"""定时任务调度器"""
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler

logger = logging.getLogger(__name__)


def init_scheduler() -> AsyncIOScheduler:
    """初始化定时任务。在 FastAPI lifespan 中启动。"""
    from backend.core.document_store import get_document_store

    scheduler = AsyncIOScheduler()
    store = get_document_store()

    # 每天 16:00 清理过期项目（14 天未访问）
    scheduler.add_job(
        store.cleanup_expired,
        "cron",
        hour=16,
        minute=0,
        kwargs={"ttl_days": 14},
        id="cleanup_expired_chunks",
        name="清理过期父子块",
    )

    scheduler.start()
    logger.info("Scheduler started — daily cleanup at 16:00")
    return scheduler
