"""ActiveBuffer — 基于 token 计数的滑动窗口"""
import logging
import tiktoken
from typing import Optional

logger = logging.getLogger(__name__)

_FALLBACK_ENCODING = "cl100k_base"


class ActiveBuffer:
    """活跃缓冲区 — 保留最近对话的完整原文，按 token 数管理窗口"""

    def __init__(self, token_limit: int = 4000, model_name: str = "gpt-4o-mini"):
        self.token_limit = token_limit
        self.model_name = model_name
        self._messages: list[dict] = []
        self._encoder = self._get_encoder(model_name)

    def _get_encoder(self, model_name: str):
        try:
            return tiktoken.encoding_for_model(model_name)
        except KeyError:
            logger.debug(f"Model '{model_name}' not in tiktoken registry, using {_FALLBACK_ENCODING}")
            return tiktoken.get_encoding(_FALLBACK_ENCODING)

    def count_tokens(self, text: str) -> int:
        return len(self._encoder.encode(text))

    def token_count(self) -> int:
        return sum(self.count_tokens(m["content"]) for m in self._messages)

    def remaining(self) -> int:
        return max(0, self.token_limit - self.token_count())

    def add_turn(self, question: str, answer: str) -> list[dict] | None:
        self._messages.append({"role": "user", "content": question})
        self._messages.append({"role": "assistant", "content": answer})

        evicted = self._evict_if_needed()
        return evicted if evicted else None

    def _evict_if_needed(self) -> list[dict]:
        evicted = []
        min_keep = 2

        while self.token_count() > self.token_limit and len(self._messages) > min_keep:
            evicted.append(self._messages.pop(0))

        if evicted:
            logger.debug(f"Evicted {len(evicted)} messages, "
                         f"remaining tokens: {self.token_count()}/{self.token_limit}")

        return evicted

    def as_messages(self) -> list[dict]:
        return list(self._messages)

    def clear(self):
        self._messages.clear()
