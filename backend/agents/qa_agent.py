"""问答 Agent - 并行多源检索 + 对话历史感知"""
import logging
from .base import BaseAgent
from backend.core.vector_store import get_vector_store
from backend.utils.web_search import web_search

logger = logging.getLogger(__name__)

QA_SYSTEM_PROMPT = """你是一个学习助手，帮助学生解答关于学习项目的问题。

你会同时收到以下信息来源，请综合判断后回答:
1. 「学习摘要」— 系统对学习材料的结构化总结，可信度最高
2. 「RAG检索结果」— 从原始文档中语义检索到的相关片段
3. 「网络搜索结果」— 外部实时搜索的结果
4. 「对话历史」— 你和用户之前的问答记录（如果有）

回答规则:
- 优先信任学习摘要和RAG检索结果
- 如果以上内部知识不足，再参考网络搜索结果
- 结合对话历史理解用户的追问和指代（如"它"、"这个"）
- 回答要准确、简洁、有针对性
- 如果所有来源都无法回答问题，坦诚告知用户
- 使用中文回答"""


class QAAgent(BaseAgent):
    def __init__(self):
        super().__init__("QAAgent")

    async def run(self, input_data: dict) -> dict:
        """回答问题"""
        question = input_data.get("question", "")
        project_id = input_data.get("project_id", "")
        summary = input_data.get("summary", "")  # 学习摘要
        raw_content = input_data.get("raw_content", "")
        history = input_data.get("history", [])  # B1: 最近 QA 历史

        if not question.strip():
            return {"answer": "请提供问题。", "source_type": "none", "available_sources": []}

        # 并行获取 RAG 和网络搜索结果
        rag_results = []
        try:
            vs = get_vector_store()
            rag_results = await vs.search(project_id, question, top_k=3)
        except Exception as e:
            logger.warning(f"RAG检索失败: {e}")

        web_results = []
        try:
            web_results = await web_search(question, max_results=3)
        except Exception as e:
            logger.warning(f"网络搜索失败: {e}")

        # 构建 prompt
        prompt_parts = [f"用户问题: {question}\n"]

        # B1: 注入对话历史，让 LLM 理解追问和指代
        if history:
            history_lines = []
            for h in history[-3:]:
                history_lines.append(f"Q: {h.get('question', '')}")
                history_lines.append(f"A: {h.get('answer', '')[:300]}")
            if history_lines:
                prompt_parts.append("## 对话历史\n" + "\n".join(history_lines))

        if summary:
            prompt_parts.append(f"## 学习摘要\n{summary[:3000]}")
        else:
            prompt_parts.append(f"## 原始内容\n{raw_content[:3000]}")

        if rag_results:
            rag_text = "\n---\n".join([r.get("text", "")[:800] for r in rag_results])
            prompt_parts.append(f"## RAG检索结果\n{rag_text}")

        if web_results:
            web_text = "\n".join([f"- [{r['title']}]({r['url']}): {r['snippet']}" for r in web_results])
            prompt_parts.append(f"## 网络搜索结果\n{web_text}")

        prompt = "\n\n".join(prompt_parts)

        # A2: 准确标记可用数据源
        available_sources = []
        if summary or raw_content:
            available_sources.append("summary")
        if rag_results:
            available_sources.append("rag")
        if web_results:
            available_sources.append("web")

        source_type = "rag" if rag_results else ("web" if web_results else "summary")

        try:
            answer = await self.think(prompt, system_prompt=QA_SYSTEM_PROMPT)
            return {
                "answer": answer,
                "source_type": source_type,
                "available_sources": available_sources,
                "rag_count": len(rag_results),
            }
        except Exception as e:
            logger.error(f"问答失败: {e}")
            return {"answer": f"抱歉，回答生成失败: {e}", "source_type": "none", "available_sources": []}


    async def stream_answer(self, question: str, summary: str, project_id: str):
        """D3: 真正的 token 级流式 SSE 输出"""
        from backend.core.llm_adapter import get_llm
        from backend.core.vector_store import get_vector_store
        from backend.utils.web_search import web_search

        yield {"type": "status", "text": "检索中..."}

        # 并行获取 RAG 和网络搜索结果
        rag_results = []
        try:
            vs = get_vector_store()
            rag_results = await vs.search(project_id, question, top_k=3)
        except Exception as e:
            logger.warning(f"RAG检索失败: {e}")

        web_results = []
        try:
            web_results = await web_search(question, max_results=3)
        except Exception as e:
            logger.warning(f"网络搜索失败: {e}")

        # 构建 prompt（与 run() 一致）
        prompt_parts = [f"用户问题: {question}\n"]

        if summary:
            prompt_parts.append(f"## 学习摘要\n{summary[:3000]}")
        else:
            from backend.core.database import get_db_session
            from backend.models.database import LearningContent
            db = get_db_session()
            try:
                content = db.query(LearningContent).filter(
                    LearningContent.project_id == project_id
                ).first()
                if content and content.raw_content:
                    prompt_parts.append(f"## 原始内容\n{content.raw_content[:3000]}")
            finally:
                db.close()

        if rag_results:
            rag_text = "\n---\n".join([r.get("text", "")[:800] for r in rag_results])
            prompt_parts.append(f"## RAG检索结果\n{rag_text}")

        if web_results:
            web_text = "\n".join([f"- [{r['title']}]({r['url']}): {r['snippet']}" for r in web_results])
            prompt_parts.append(f"## 网络搜索结果\n{web_text}")

        prompt = "\n\n".join(prompt_parts)

        available_sources = []
        if summary:
            available_sources.append("summary")
        if rag_results:
            available_sources.append("rag")
        if web_results:
            available_sources.append("web")

        source_type = "rag" if rag_results else ("web" if web_results else "summary")

        yield {"type": "status", "text": "生成中..."}

        # D3: 真正的 token 级流式输出
        llm = get_llm()
        try:
            async for chunk in llm.astream(prompt, system_prompt=QA_SYSTEM_PROMPT):
                yield {"type": "chunk", "text": chunk}
        except Exception as e:
            logger.error(f"流式生成失败: {e}")
            yield {"type": "error", "text": str(e)}
            return

        yield {
            "type": "done",
            "source_type": source_type,
            "available_sources": available_sources,
        }
