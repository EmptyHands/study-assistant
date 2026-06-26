"""Framework analysis agent"""
import logging
from .base import BaseAgent

logger = logging.getLogger(__name__)

FRAMEWORK_PROMPT = """Analyze this learning material and extract its structural framework.

Return ONLY valid JSON:
{{"framework_type": "tree/flow/list/hierarchy", "title": "title", "overview": "one-line summary", "structure": [{{"id": "1", "title": "section", "description": "desc", "children": []}}], "key_concepts": ["concept1"], "prerequisites": [], "estimated_scope": "small/medium/large"}}

Content:
{content}"""


class FrameworkAgent(BaseAgent):
    def __init__(self):
        super().__init__("FrameworkAgent")

    async def run(self, input_data: dict) -> dict:
        content = input_data.get("raw_content", "")[:10000]
        prompt = FRAMEWORK_PROMPT.replace("{content}", content)
        try:
            response = await self.think(prompt, system_prompt="You are a knowledge structure analyst. Return ONLY valid JSON.")
            framework = self.safe_json(response, {})
            return {"success": True, "framework": framework}
        except Exception as e:
            logger.error(f"Framework analysis failed: {e}")
            return {"success": False, "error": str(e), "framework": {}}
