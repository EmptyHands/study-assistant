"""ConversationContext — 对话上下文协调器"""
import logging
from .active_buffer import ActiveBuffer
from .background_knowledge import BackgroundKnowledgeStore

logger = logging.getLogger(__name__)


class ConversationContext:
    """对话上下文 — 组合 ActiveBuffer + BackgroundKnowledgeStore"""

    def __init__(self, project_id: str, token_limit: int = 4000,
                 model_name: str = "gpt-4o-mini"):
        self.project_id = project_id
        self.buffer = ActiveBuffer(token_limit=token_limit, model_name=model_name)
        self.store = BackgroundKnowledgeStore(project_id=project_id)
        self._summary_loaded = False
        self._background_text: str = ""

    def add_turn(self, question: str, answer: str):
        evicted = self.buffer.add_turn(question, answer)

        if evicted:
            logger.debug(f"Evicted {len(evicted)} messages from buffer, "
                         f"scheduling summary update")
            import asyncio
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(self._do_summarize(evicted))
            except RuntimeError:
                asyncio.run(self._do_summarize(evicted))

    async def _do_summarize(self, evicted: list[dict]):
        self._background_text = ""
        await self.store.update(evicted)

    def build_system_prompt_addition(self) -> str:
        if self._background_text:
            return self._background_text

        knowledge = self.store.load()
        if knowledge is None:
            return ""

        self._background_text = self.store.format_for_prompt(knowledge)
        return self._background_text

    def build_chat_history(self) -> list[dict]:
        return self.buffer.as_messages()

    async def flush(self):
        pass
