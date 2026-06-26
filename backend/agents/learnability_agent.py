"""Learnability check agent"""
import logging
from .base import BaseAgent

logger = logging.getLogger(__name__)

LEARNABILITY_PROMPT = """You are a learning material evaluation expert. Determine if the following content is suitable as a learning project.

Learnable: tutorials, textbooks, academic papers, structured code projects, flowcharts, knowledge systems, concepts with clear structure.
Not learnable: scenic photos, receipts/invoices, raw data spreadsheets, awesome-list repos, cache/temp files, advertisements, disorganized notes.

Return ONLY valid JSON (no markdown, no extra text):
{"is_learnable": true, "reason": "brief reason", "content_type": "type", "title": "suggested title"}

Content:
{content}"""


class LearnabilityAgent(BaseAgent):
    def __init__(self):
        super().__init__("LearnabilityAgent")

    async def run(self, input_data: dict) -> dict:
        content = input_data.get("raw_content", "")
        if not content or not content.strip():
            return {"is_learnable": False, "reason": "empty content", "content_type": "empty", "title": ""}
        truncated = content[:8000] if len(content) > 8000 else content
        prompt = LEARNABILITY_PROMPT.replace("{content}", truncated)
        try:
            response = await self.think(prompt, system_prompt="You are a learning material evaluator. Return ONLY valid JSON.")
            result = self.safe_json(response, {"is_learnable": False, "reason": "parse failed", "content_type": "", "title": ""})
            return {
                "is_learnable": result.get("is_learnable", False),
                "reason": result.get("reason", ""),
                "content_type": result.get("content_type", ""),
                "title": result.get("title", ""),
            }
        except Exception as e:
            logger.error(f"Learnability check failed: {e}")
            return {"is_learnable": False, "reason": f"error: {e}", "content_type": "", "title": ""}
