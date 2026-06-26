"""学习日志 Agent - 整理知识总结和薄弱点分析"""
import json
import logging
from datetime import date
from .base import BaseAgent

logger = logging.getLogger(__name__)

LOG_SUMMARY_PROMPT = """你是一个学习分析专家。请基于用户的学习活动记录，整理一份学习摘要。

## 学习项目: {title}

## 问答记录:
{qa_records}

## 费曼学习记录:
{feynman_records}

请返回JSON格式:
{{
  "knowledge_summary": "对用户已掌握知识点的梳理（Markdown格式）",
  "weak_points": "用户薄弱点的概括，以及针对性建议",
  "progress_rating": "beginner/intermediate/advanced",
  "recommendations": ["学习建议1", "建议2"]
}}"""


class LogAgent(BaseAgent):
    def __init__(self):
        super().__init__("LogAgent")

    async def generate_log(self, context: dict) -> dict:
        """生成学习日志摘要"""
        title = context.get("title", "")
        qa_records = context.get("qa_records", [])
        feynman_records = context.get("feynman_records", [])

        qa_text = "\n".join([f"Q: {r.get('question', '')}\nA: {r.get('answer', '')[:300]}" for r in qa_records[-10:]])
        feynman_text = json.dumps(feynman_records[-5:], ensure_ascii=False)

        if not qa_text and not feynman_records:
            return {
                "knowledge_summary": "暂无学习记录",
                "weak_points": "",
                "progress_rating": "beginner",
                "recommendations": ["开始使用问答功能来检验学习效果", "尝试费曼学习法来加深理解"],
            }

        prompt = LOG_SUMMARY_PROMPT.replace("{title}", title).replace("{qa_records}", qa_text or "no records").replace("{feynman_records}", feynman_text or "no records")

        try:
            response = await self.think(prompt, system_prompt="你是一个学习分析专家。请只返回JSON。")
            return self.parse_json_response(response)
            return {"knowledge_summary": "", "weak_points": "", "progress_rating": "beginner", "recommendations": []}
        except Exception as e:
            logger.error(f"生成日志摘要失败: {e}")
            return {"knowledge_summary": "", "weak_points": "", "progress_rating": "beginner", "recommendations": []}

    async def supplement_content(self, existing_content: dict, raw_content: str) -> dict:
        """补充学习内容 - 少修改、多补充"""
        prompt = f"""请分析现有的学习讲解，找出可以补充的内容。规则:
1. 尽量不修改原有内容，只在合适的位置补充
2. 可以补充的内容包括: 遗漏的概念细节、实际例子、相关知识点对比
3. 如果现有内容已经比较完整，请指出不需要补充

现有讲解:
{json.dumps(existing_content, ensure_ascii=False, indent=2)[:5000]}

原始材料（部分）:
{raw_content[:3000]}

返回JSON:
{{"needs_update": true/false, "supplements": [{{"section": "在哪个部分补充", "content": "补充内容(Markdown)"}}], "reason": "补充理由"}}"""

        try:
            response = await self.think(prompt, system_prompt="你是一个严谨的内容编辑。请只返回JSON。")
            return self.parse_json_response(response)
            return {"needs_update": False, "supplements": [], "reason": "无法分析"}
        except Exception as e:
            logger.error(f"补充内容失败: {e}")
            return {"needs_update": False, "supplements": [], "reason": str(e)}

    async def run(self, input_data: dict) -> dict:
        action = input_data.get("action", "generate_log")
        if action == "generate_log":
            return await self.generate_log(input_data.get("context", {}))
        elif action == "supplement":
            return await self.supplement_content(
                input_data.get("existing_content", {}),
                input_data.get("raw_content", ""),
            )
        return {"error": "未知操作"}
