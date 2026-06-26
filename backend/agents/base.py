"""Base Agent abstract class"""
import json
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Optional
from backend.core.llm_adapter import get_llm

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    def __init__(self, name: str):
        self.name = name
        self.llm = get_llm()
        self.history: list[str] = []
        self.state = "idle"

    @abstractmethod
    async def run(self, input_data: dict[str, Any]) -> dict[str, Any]:
        """execute agent task"""

    async def think(self, prompt: str, system_prompt: str = None, **kwargs) -> str:
        try:
            response = await self.llm.ainvoke(prompt, system_prompt=system_prompt, **kwargs)
            self._log(f"LLM response length: {len(response)}")
            return response
        except Exception as e:
            logger.error(f"[{self.name}] LLM call failed: {e}")
            raise

    def parse_json_response(self, text: str) -> dict:
        """Robust JSON extraction from LLM responses"""
        if not text or not text.strip():
            raise ValueError("empty response")
        text = text.strip()
        # Remove BOM and control chars before first {
        for i, ch in enumerate(text):
            if ch == "{":
                text = text[i:]
                break
        md_match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
        if md_match:
            text = md_match.group(1)
        start = text.find("{")
        end = text.rfind("}") + 1
        if start >= 0 and end > start:
            text = text[start:end]
        text = re.sub(r",\s*}", "}", text)
        text = re.sub(r",\s*]", "]", text)
        return json.loads(text)

    def safe_json(self, text: str, default: dict = None) -> dict:
        try:
            return self.parse_json_response(text)
        except Exception as e:
            logger.warning(f"[{self.name}] JSON parse failed: {e}, raw={text[:200]}")
            return default or {}

    def _log(self, message: str):
        ts = datetime.now().strftime("%H:%M:%S")
        entry = f"[{ts}] {message}"
        self.history.append(entry)
        if len(self.history) > 100:
            self.history = self.history[-50:]

    def get_status(self) -> dict:
        return {"name": self.name, "state": self.state, "history_count": len(self.history)}
