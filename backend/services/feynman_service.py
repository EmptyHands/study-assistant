"""费曼学习服务"""
import logging
import json
from backend.core.database import get_db_session
from backend.models.database import Project, FeynmanSession, LearningContent
from backend.core.exceptions import NotFoundException
from backend.agents.feynman_agent import FeynmanAgent

logger = logging.getLogger(__name__)


async def start_feynman_session(project_id: str) -> dict:
    """开始一个新的费曼学习会话"""
    db = get_db_session()
    try:
        project = db.query(Project).filter(Project.id == project_id).first()
        if not project:
            raise NotFoundException(f"项目不存在: {project_id}")

        content = db.query(LearningContent).filter(LearningContent.project_id == project_id).first()
        if not content:
            raise NotFoundException("学习内容尚未生成，请先启动学习")

        framework = content.framework_json or {}
        title = content.title or project.name
        key_concepts = framework.get("key_concepts", [])

        agent = FeynmanAgent()
        question_data = await agent.generate_question({
            "title": title,
            "framework": framework,
            "key_concepts": key_concepts,
            "history": [],
        })

        session = FeynmanSession(
            project_id=project_id,
            session_data=[{
                "round": 1,
                "question": question_data.get("question", ""),
                "question_type": question_data.get("question_type", ""),
                "focus": question_data.get("focus", ""),
                "hint": question_data.get("hint", ""),
                "answer": None,
                "evaluation": None,
            }],
            status="active",
        )
        db.add(session)
        db.commit()
        db.refresh(session)

        return {
            "session_id": session.id,
            "question": question_data.get("question", ""),
            "question_type": question_data.get("question_type", ""),
            "hint": question_data.get("hint", ""),
            "round": 1,
        }
    finally:
        db.close()


async def submit_answer(session_id: str, answer: str, confused: bool = False) -> dict:
    """提交用户回答"""
    db = get_db_session()
    try:
        session = db.query(FeynmanSession).filter(FeynmanSession.id == session_id).first()
        if not session:
            raise NotFoundException("会话不存在")
        if session.status != "active":
            raise NotFoundException("会话已结束")

        session_data = session.session_data or []
        project = db.query(Project).filter(Project.id == session.project_id).first()
        content = db.query(LearningContent).filter(LearningContent.project_id == session.project_id).first()

        title = content.title if content else (project.name if project else "")
        framework = content.framework_json if content else {}

        # 更新上一轮的答案
        if session_data:
            last = session_data[-1]
            last["answer"] = answer
            last["confused"] = confused

        agent = FeynmanAgent()

        # 评估答案
        if not confused:
            evaluation = await agent.evaluate_answer({
                "title": title,
                "question": last.get("question", ""),
                "answer": answer,
            })
            last["evaluation"] = evaluation
            correction = evaluation.get("correction", "")
            follow_up = evaluation.get("follow_up_action", "next_question")
        else:
            evaluation = {"understanding_level": "poor", "correction": "没关系！让我们一起来理解这个问题。", "follow_up_action": "clarify"}
            last["evaluation"] = evaluation
            correction = "没关系！让我们一起来理解这个问题。"
            follow_up = "clarify"

        # 生成下一个问题
        max_rounds = 8
        if len(session_data) >= max_rounds:
            # 结束会话
            session.status = "completed"
            summary_agent = FeynmanAgent()
            summary = await summary_agent.summarize_session(session_data)
            session.weak_points = summary
            db.commit()
            return {
                "session_completed": True,
                "evaluation": evaluation,
                "correction": correction,
                "weak_points": summary.get("weak_points", []),
                "overall_assessment": summary.get("overall_assessment", ""),
            }

        next_question = await agent.generate_question({
            "title": title,
            "framework": framework,
            "key_concepts": framework.get("key_concepts", []),
            "history": session_data,
        })

        session_data.append({
            "round": len(session_data) + 1,
            "question": next_question.get("question", ""),
            "question_type": next_question.get("question_type", ""),
            "focus": next_question.get("focus", ""),
            "hint": next_question.get("hint", ""),
            "answer": None,
            "evaluation": None,
        })
        session.session_data = session_data
        db.commit()

        return {
            "session_completed": False,
            "evaluation": evaluation,
            "correction": correction,
            "next_question": next_question.get("question", ""),
            "question_type": next_question.get("question_type", ""),
            "hint": next_question.get("hint", ""),
            "round": len(session_data),
        }
    finally:
        db.close()
