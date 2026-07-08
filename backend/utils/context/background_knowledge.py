"""BackgroundKnowledge — 对话历史摘要的生成、持久化与格式化"""
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from backend.core.database import get_db_session
from backend.models.database import ProjectBackgroundKnowledge

logger = logging.getLogger(__name__)

SUMMARY_PROMPT = """你是一个对话摘要助手。请根据以下增量对话，更新历史摘要。

## 当前摘要
用户意图：{user_intents}
助手行动：{assistant_actions}
关键事实：{key_facts}

## 新增对话
{new_messages}

## 输出要求
请以 JSON 格式输出更新后的摘要，包含以下三个字段：
- user_intents: 用户的主要问题和目标
- assistant_actions: 助手提供了哪些信息或执行了哪些操作
- key_facts: 对话中确认的重要事实、决定或偏好

请确保摘要简洁，保留所有关键信息，不要编造内容。
输出格式：{{"user_intents": "...", "assistant_actions": "...", "key_facts": "..."}}"""


@dataclass
class BackgroundKnowledge:
    """背景知识 — 窗口外历史的压缩摘要"""
    user_intents: str = ""
    assistant_actions: str = ""
    key_facts: str = ""
    message_count: int = 0
    last_updated: Optional[datetime] = None


class BackgroundKnowledgeStore:
    """背景知识存储 — 负责摘要的生成、DB 读写、格式化"""

    def __init__(self, project_id: str):
        self.project_id = project_id

    def load(self) -> Optional[BackgroundKnowledge]:
        db = get_db_session()
        try:
            row = db.query(ProjectBackgroundKnowledge).filter(
                ProjectBackgroundKnowledge.project_id == self.project_id
            ).first()
            if row is None:
                return None
            return BackgroundKnowledge(
                user_intents=row.user_intents or "",
                assistant_actions=row.assistant_actions or "",
                key_facts=row.key_facts or "",
                message_count=row.message_count or 0,
                last_updated=row.updated_at,
            )
        finally:
            db.close()

    def save(self, knowledge: BackgroundKnowledge):
        db = get_db_session()
        try:
            row = db.query(ProjectBackgroundKnowledge).filter(
                ProjectBackgroundKnowledge.project_id == self.project_id
            ).first()
            if row:
                row.user_intents = knowledge.user_intents
                row.assistant_actions = knowledge.assistant_actions
                row.key_facts = knowledge.key_facts
                row.message_count = knowledge.message_count
                row.updated_at = datetime.utcnow()
            else:
                row = ProjectBackgroundKnowledge(
                    project_id=self.project_id,
                    user_intents=knowledge.user_intents,
                    assistant_actions=knowledge.assistant_actions,
                    key_facts=knowledge.key_facts,
                    message_count=knowledge.message_count,
                )
                db.add(row)
            db.commit()
        finally:
            db.close()

    async def update(self, evicted_messages: list[dict]) -> BackgroundKnowledge:
        current = self.load() or BackgroundKnowledge()

        new_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else '助手'}: {m['content']}"
            for m in evicted_messages
        )

        prompt = SUMMARY_PROMPT.format(
            user_intents=current.user_intents or "（无）",
            assistant_actions=current.assistant_actions or "（无）",
            key_facts=current.key_facts or "（无）",
            new_messages=new_text,
        )

        try:
            from backend.core.llm_adapter import get_summary_llm
            llm = get_summary_llm()
            if llm is None:
                logger.warning("No summary LLM available, skipping summarization")
                return current

            response = await llm.ainvoke(prompt)
            data = self._parse_summary_response(response)

            updated = BackgroundKnowledge(
                user_intents=data.get("user_intents", current.user_intents),
                assistant_actions=data.get("assistant_actions", current.assistant_actions),
                key_facts=data.get("key_facts", current.key_facts),
                message_count=current.message_count + len(evicted_messages),
                last_updated=datetime.utcnow(),
            )

            self.save(updated)
            logger.info(f"Summary updated for project {self.project_id}, "
                        f"total messages summarized: {updated.message_count}")
            return updated

        except Exception as e:
            logger.warning(f"Summary LLM call failed: {e}, keeping existing summary")
            return current

    def _parse_summary_response(self, response: str) -> dict:
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            pass
        import re
        match = re.search(r'```(?:json)?\s*([\s\S]*?)```', response)
        if match:
            try:
                return json.loads(match.group(1))
            except json.JSONDecodeError:
                pass
        start = response.find('{')
        end = response.rfind('}') + 1
        if start >= 0 and end > start:
            try:
                return json.loads(response[start:end])
            except json.JSONDecodeError:
                pass
        logger.warning(f"Failed to parse summary response: {response[:200]}")
        return {}

    def format_for_prompt(self, knowledge: BackgroundKnowledge) -> str:
        parts = []
        if knowledge.user_intents:
            parts.append(f"- 用户之前关心的问题: {knowledge.user_intents}")
        if knowledge.assistant_actions:
            parts.append(f"- 之前已讨论的内容: {knowledge.assistant_actions}")
        if knowledge.key_facts:
            parts.append(f"- 已确认的事实: {knowledge.key_facts}")

        if not parts:
            return ""

        return "## 对话历史背景\n" + "\n".join(parts)
