"""学习日志服务"""
import logging
from datetime import date, datetime
from backend.core.database import get_db_session
from backend.models.database import Project, LearningLog, QARecord, FeynmanSession, LearningContent
from backend.core.exceptions import NotFoundException
from backend.agents.log_agent import LogAgent

logger = logging.getLogger(__name__)


async def generate_daily_log(project_id: str) -> dict:
    """生成今日学习日志"""
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise NotFoundException(f"项目不存在: {project_id}")

        today = date.today()
        content = db.query(LearningContent).filter(LearningContent.project_id == project_id).first()

        # 获取今天的问答记录
        qa_records = (
            db.query(QARecord)
            .filter(QARecord.project_id == project_id)
            .filter(QARecord.created_at >= today)
            .all()
        )
        qa_list = [{"question": r.question, "answer": r.answer[:300]} for r in qa_records]

        # 获取今天的费曼会话
        feynman_sessions = (
            db.query(FeynmanSession)
            .filter(FeynmanSession.project_id == project_id)
            .filter(FeynmanSession.created_at >= today)
            .all()
        )
        feynman_data = []
        for fs in feynman_sessions:
            feynman_data.extend(fs.session_data or [])

        if not qa_list and not feynman_data:
            return {"message": "今天还没有学习记录", "log": None}

        agent = LogAgent()
        summary = await agent.generate_log({
            "title": content.title if content else project.name,
            "qa_records": qa_list,
            "feynman_records": feynman_data,
        })

        # 保存日志
        existing_log = (
            db.query(LearningLog)
            .filter(LearningLog.project_id == project_id, LearningLog.log_date == today)
            .first()
        )

        session_count = len(qa_records) + len(feynman_sessions)
        if existing_log:
            existing_log.knowledge_summary = summary.get("knowledge_summary", "")
            existing_log.weak_points = summary.get("weak_points", "")
            existing_log.session_count = session_count
        else:
            log_entry = LearningLog(
                project_id=project_id,
                log_date=today,
                knowledge_summary=summary.get("knowledge_summary", ""),
                weak_points=summary.get("weak_points", ""),
                session_count=session_count,
            )
            db.add(log_entry)

        db.commit()
        return {"message": "日志已生成", "log": summary}
    finally:
        db.close()


def get_project_logs(project_id: str, limit: int = 30) -> list[dict]:
    """获取项目学习日志"""
    db = get_db_session()
    try:
        logs = (
            db.query(LearningLog)
            .filter(LearningLog.project_id == project_id)
            .order_by(LearningLog.log_date.desc())
            .limit(limit)
            .all()
        )
        return [
            {
                "id": l.id,
                "log_date": str(l.log_date) if l.log_date else None,
                "knowledge_summary": l.knowledge_summary,
                "weak_points": l.weak_points,
                "session_count": l.session_count,
            }
            for l in logs
        ]
    finally:
        db.close()


def get_latest_log(project_id: str) -> dict:
    """获取最新的学习摘要"""
    db = get_db_session()
    try:
        log = (
            db.query(LearningLog)
            .filter(LearningLog.project_id == project_id)
            .order_by(LearningLog.log_date.desc())
            .first()
        )
        if not log:
            return {"message": "暂无学习日志", "log": None}
        return {
            "log_date": str(log.log_date) if log.log_date else None,
            "knowledge_summary": log.knowledge_summary,
            "weak_points": log.weak_points,
            "session_count": log.session_count,
        }
    finally:
        db.close()


def check_update_needed(project_id: str) -> dict:
    """检查是否需要提醒用户更新"""
    db = get_db_session()
    try:
        content = db.query(LearningContent).filter(LearningContent.project_id == project_id).first()
        if not content:
            return {"update_needed": False, "reason": "学习内容不存在"}

        last_update = content.updated_at
        latest_log = (
            db.query(LearningLog)
            .filter(LearningLog.project_id == project_id)
            .order_by(LearningLog.log_date.desc())
            .first()
        )

        needs_update = False
        reason = ""
        if last_update:
            days_since_update = (datetime.utcnow() - last_update).days
            if days_since_update > 7:
                needs_update = True
                reason = f"上次更新已是 {days_since_update} 天前"
        if latest_log and latest_log.log_date:
            days_since_log = (date.today() - latest_log.log_date).days
            if days_since_log > 3:
                needs_update = True
                reason = f"上次学习日志已是 {days_since_log} 天前"

        return {"update_needed": needs_update, "reason": reason if needs_update else "内容最新"}
    finally:
        db.close()
