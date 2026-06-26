"""费曼学习法 Agent - AI 扮演好奇的学生提问"""
import json
import logging
from .base import BaseAgent

logger = logging.getLogger(__name__)

QUESTION_GEN_PROMPT = """You are using the Feynman learning method. Act as a curious student who knows nothing about this topic but wants to learn."学生"。

你需要向用户（作为"老师"）提出一个问题。规则:
1. Start from the basics and go deeper
2. Use simple, curious language
3. 不要问过于宽泛的问题（如"这个主题是什么"），要具体
4. Follow up on unclear answers from history
5. If user was confused before, help them first

主题信息:
标题: {title}
框架: {framework}
关键概念: {concepts}

{history_section}

请按以下 JSON 格式返回（不要包含其他内容）:
{{
  "question": "你的问题",
  "question_type": "basic/deep/comparison/application", 
  "focus": "这个问题关注的知识点",
  "hint": "一个简短的提示（可选，帮助用户思考）"
}}"""

EVALUATE_ANSWER_PROMPT = """You are a learning evaluator. The user is trying to explain a concept.

主题: {title}
当前问题: {question}
用户的回答: {answer}

请评估用户的回答，并返回 JSON:
{{
  "understanding_level": "good/partial/poor",
  "strengths": ["回答中好的地方"],
  "weaknesses": ["不准确或遗漏的地方"],
  "correction": "需要纠正的内容（如果有），使用友好、鼓励的语气",
  "follow_up_action": "next_question/probe_deeper/clarify"
}}"""


class FeynmanAgent(BaseAgent):
    def __init__(self):
        super().__init__("FeynmanAgent")

    async def generate_question(self, context: dict) -> dict:
        """生成下一个问题"""
        title = context.get("title", "当前主题")
        framework = json.dumps(context.get("framework", {}), ensure_ascii=False)
        concepts = ", ".join(context.get("key_concepts", []))
        history = context.get("history", [])

        history_section = ""
        if history:
            recent = history[-6:]  # 最近3轮对话
            history_section = "之前的对话历史:\n" + "\n".join(
                [f"- 问: {h.get('question', '')}\n  答: {h.get('answer', '')[:200]}" for h in recent]
            )

        prompt = QUESTION_GEN_PROMPT.replace("{title}", title).replace("{framework}", framework).replace("{concepts}", concepts).replace("{history_section}", history_section)

        try:
            response = await self.think(prompt, system_prompt="你是一个好奇的学生。请只返回JSON。")
            return self.parse_json_response(response)
            return {"question": "你能用简单的话给我讲讲这个主题吗？", "question_type": "basic", "focus": "整体理解", "hint": ""}
        except Exception as e:
            logger.error(f"生成问题失败: {e}")
            return {"question": "请继续讲解。", "question_type": "basic", "focus": "", "hint": ""}

    async def evaluate_answer(self, context: dict) -> dict:
        """评估用户的回答"""
        prompt = EVALUATE_ANSWER_PROMPT.replace("{title}", context.get("title", "")).replace("{question}", context.get("question", "")).replace("{answer}", context.get("answer", ""))

        try:
            response = await self.think(prompt, system_prompt="你是一个友善的学习评估者。请只返回JSON。")
            return self.parse_json_response(response)
            return {
                "understanding_level": "partial",
                "strengths": [],
                "weaknesses": [],
                "correction": "",
                "follow_up_action": "next_question",
            }
        except Exception as e:
            logger.error(f"评估回答失败: {e}")
            return {
                "understanding_level": "partial",
                "strengths": [],
                "weaknesses": [],
                "correction": "",
                "follow_up_action": "next_question",
            }

    async def summarize_session(self, session_data: list) -> dict:
        """总结费曼学习会话，提取薄弱点"""
        if not session_data:
            return {"weak_points": [], "knowledge_summary": ""}

        dialogue = "\n".join([
            f"Q: {item.get('question', '')}\nA: {item.get('answer', '')}\n评估: {item.get('evaluation', {}).get('understanding_level', '')}"
            for item in session_data
        ])

        summary_prompt = f"""请总结以下费曼学习对话，提取:
1. 用户的知识薄弱点
2. 用户掌握较好的知识点

对话记录:
{dialogue}

返回JSON:
{"weak_points": [], "strengths": [], "overall_assessment": ""}"""

        try:
            response = await self.think(summary_prompt)
            json_start = response.find("{")
            json_end = response.rfind("}") + 1
            if json_start >= 0 and json_end > json_start:
                result = json.loads(response[json_start:json_end])
                return result
            return {"weak_points": [], "strengths": [], "overall_assessment": ""}
        except Exception as e:
            logger.error(f"总结会话失败: {e}")
            return {"weak_points": [], "strengths": [], "overall_assessment": ""}

    async def run(self, input_data: dict) -> dict:
        action = input_data.get("action", "generate_question")
        if action == "generate_question":
            return await self.generate_question(input_data.get("context", {}))
        elif action == "evaluate_answer":
            return await self.evaluate_answer(input_data.get("context", {}))
        elif action == "summarize":
            return await self.summarize_session(input_data.get("session_data", []))
        return {"error": "未知操作"}
