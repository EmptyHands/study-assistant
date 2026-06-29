"""Content explanation agent (SQ3R)"""
import logging
from .base import BaseAgent

logger = logging.getLogger(__name__)

EXPLANATION_PROMPT = """你是一位优秀的老师。请用 SQ3R 格式生成一份简洁的学习讲解。每个部分不超过500字，尽量使用简洁的要点列表。

只返回合法的JSON（总回复不超过3000字）:
{{"title": "学习标题", "sq3r": {{"survey": {{"title": "概览", "content": "markdown格式的概述"}}, "question": {{"title": "提问", "questions": ["问题1", "问题2", "问题3"], "guidance": "阅读时请尝试回答这些问题"}}, "read": {{"title": "阅读", "sections": [{{"heading": "章节标题", "content": "markdown格式的详细讲解"}}]}}, "recite": {{"title": "复述", "key_points": ["关键点1"], "summary": "总结"}}, "review": {{"title": "复习", "suggestions": ["建议1"], "exercises": ["练习1"]}}}}}}

框架:
{framework}

原始内容（部分）:
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
            response = await self.think(prompt, system_prompt="你是一位优秀的老师。只返回合法的JSON。")
            result = self.safe_json(response, {})
            return {"success": True, "explanation": result.get("sq3r", {}), "title": result.get("title", "")}
        except Exception as e:
            logger.error(f"Explanation failed: {e}")
            return {"success": False, "error": str(e), "explanation": {}, "title": ""}
