"""Learnability check agent"""
import logging
from .base import BaseAgent

logger = logging.getLogger(__name__)

LEARNABILITY_PROMPT = """你是一个学习材料评估专家。请判断以下内容是否适合作为学习项目。

适合学习: 教程、教材、学术论文、结构化代码项目、流程图、知识体系、具有清晰结构的概念。
不适合学习: 风景照片、收据/发票、原始数据表格、awesome-list仓库、缓存/临时文件、广告、杂乱无章的笔记。

只返回合法的JSON（不要markdown，不要额外文字）:
{{"is_learnable": true, "reason": "简要说明", "content_type": "类型", "title": "建议的标题"}}

内容:
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
            response = await self.think(prompt, system_prompt="你是一个学习材料评估专家。只返回合法的JSON。")
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
