"""费曼学习法 Agent - AI 扮演好奇的学生提问"""
import json
import logging
from .base import BaseAgent

logger = logging.getLogger(__name__)

QUESTION_GEN_PROMPT = """你正在使用费曼学习法。扮演一个对这个主题一无所知但渴望学习的好奇学生。

你需要向用户（作为"老师"）提出一个问题。规则:
1. 从基础开始，逐步深入
2. 使用简单、好奇的语言
3. 不要问过于宽泛的问题（如"这个主题是什么"），要具体
4. 针对历史记录中不清楚的回答进行追问
5. 如果用户之前表现出困惑，先帮助ta理解

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

EVALUATE_ANSWER_PROMPT = """你是一个学习评估专家。用户正在尝试解释一个概念。

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


EXPLAIN_QUESTION_PROMPT = """你是一个友善、耐心的老师。学生对你提出的问题感到困惑，不确定如何回答。

主题: {title}
学生困惑的问题: {question}

请用简单易懂的语言解释这个问题：
1. 把问题拆解成更简单的部分
2. 用通俗的比喻或例子帮助理解
3. 解释这个问题考察的关键概念是什么
4. 保持鼓励的语气，让学生感到安心

请用自然段落回复（不要用JSON），保持友好、鼓励的语气。回复不要过长，3-5句话即可。"""


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

    async def explain_question(self, context: dict) -> dict:
        """当用户表示困惑时，用简单语言解释当前问题"""
        question = context.get("question", "").strip()
        if not question:
            return {"explanation": "没关系！让我们一起来理解这个问题。"}

        prompt = EXPLAIN_QUESTION_PROMPT.replace(
            "{title}", context.get("title", "")
        ).replace("{question}", question)

        try:
            explanation = await self.think(prompt, system_prompt="你是一个友善、耐心的老师。")
            return {"explanation": explanation.strip()}
        except Exception as e:
            logger.error(f"解释问题失败: {e}")
            return {"explanation": "没关系！让我们一起来理解这个问题。"}

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
        elif action == "explain_question":
            return await self.explain_question(input_data.get("context", {}))
        return {"error": "未知操作"}
