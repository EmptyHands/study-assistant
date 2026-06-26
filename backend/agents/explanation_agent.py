"""Content explanation agent (SQ3R)"""
import logging
from .base import BaseAgent

logger = logging.getLogger(__name__)

EXPLANATION_PROMPT = """You are an excellent teacher. Generate a CONCISE learning explanation in SQ3R format. Keep each section under 500 characters, use brief bullet points where possible.

Return ONLY valid JSON (keep total response under 3000 chars):
{{"title": "learning title", "sq3r": {{"survey": {{"title": "Survey", "content": "overview in markdown"}}, "question": {{"title": "Questions", "questions": ["Q1", "Q2", "Q3"], "guidance": "answer these while reading"}}, "read": {{"title": "Read", "sections": [{{"heading": "section title", "content": "detailed explanation in markdown"}}]}}, "recite": {{"title": "Recite", "key_points": ["key point 1"], "summary": "summary"}}, "review": {{"title": "Review", "suggestions": ["tip 1"], "exercises": ["exercise 1"]}}}}}}

Framework:
{framework}

Original content (partial):
{content}"""


class ExplanationAgent(BaseAgent):
    def __init__(self):
        super().__init__("ExplanationAgent")

    async def run(self, input_data: dict) -> dict:
        import json as _json
        content = input_data.get("raw_content", "")[:8000]
        framework = input_data.get("framework", {})
        framework_str = _json.dumps(framework, ensure_ascii=False, indent=2)
        prompt = EXPLANATION_PROMPT.format(framework=framework_str, content=content)
        try:
            response = await self.think(prompt, system_prompt="You are an excellent teacher. Return ONLY valid JSON.")
            result = self.safe_json(response, {})
            return {"success": True, "explanation": result.get("sq3r", {}), "title": result.get("title", "")}
        except Exception as e:
            logger.error(f"Explanation failed: {e}")
            return {"success": False, "error": str(e), "explanation": {}, "title": ""}
