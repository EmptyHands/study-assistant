"""Framework analysis agent"""
import logging
from .base import BaseAgent

logger = logging.getLogger(__name__)

FRAMEWORK_PROMPT = """请分析这份学习材料，提取其结构框架。

只返回合法的JSON:
{{"framework_type": "tree/flow/list/hierarchy", "title": "标题", "overview": "一句话概述", "structure": [{{"id": "1", "title": "章节标题", "description": "描述", "children": []}}], "key_concepts": ["关键概念1"], "prerequisites": [], "estimated_scope": "small/medium/large"}}

内容:
{content}"""


class FrameworkAgent(BaseAgent):
    def __init__(self):
        super().__init__("FrameworkAgent")

    async def run(self, input_data: dict) -> dict:
        content = input_data.get("raw_content", "")[:10000]
        prompt = FRAMEWORK_PROMPT.replace("{content}", content)
        try:
            response = await self.think(prompt, system_prompt="你是一个知识结构分析专家。只返回合法的JSON。")
            framework = self.safe_json(response, {})
            return {"success": True, "framework": framework}
        except Exception as e:
            logger.error(f"Framework analysis failed: {e}")
            return {"success": False, "error": str(e), "framework": {}}
