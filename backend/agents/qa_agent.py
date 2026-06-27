"""问答 Agent - RAG + 摘要 + 网络搜索"""
import logging
from .base import BaseAgent
from backend.core.vector_store import get_vector_store
from backend.utils.web_search import web_search

logger = logging.getLogger(__name__)

QA_SYSTEM_PROMPT = """你是一个学习助手，帮助学生解答关于学习项目的问题。

回答规则:
1. 优先使用提供的"学习摘要"来回答问题
2. 如果摘要信息不足，使用提供的"RAG检索结果"（从原始文档中检索）
3. 如果以上都不够，使用"网络搜索结果"
4. 回答要准确、简洁、有针对性
5. 如果所有来源都无法回答问题，坦诚告知用户
6. 使用中文回答"""


class QAAgent(BaseAgent):
    def __init__(self):
        super().__init__("QAAgent")

    async def run(self, input_data: dict) -> dict:
        """回答问题"""
        question = input_data.get("question", "")
        project_id = input_data.get("project_id", "")
        summary = input_data.get("summary", "")  # 学习摘要
        raw_content = input_data.get("raw_content", "")

        if not question.strip():
            return {"answer": "请提供问题。", "source_type": "none"}

        # 尝试 RAG 检索
        rag_results = []
        try:
            vs = get_vector_store()
            rag_results = await vs.search(project_id, question, top_k=3)
        except Exception as e:
            logger.warning(f"RAG检索失败: {e}")

        # 尝试网络搜索
        web_results = []
        try:
            web_results = await web_search(question, max_results=3)
        except Exception as e:
            logger.warning(f"网络搜索失败: {e}")

        # 构建 prompt
        prompt_parts = [f"用户问题: {question}\n"]

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

        # 判断来源
        if rag_results:
            source_type = "rag"
        elif web_results:
            source_type = "web"
        else:
            source_type = "summary"

        try:
            answer = await self.think(prompt, system_prompt=QA_SYSTEM_PROMPT)
            return {"answer": answer, "source_type": source_type, "rag_count": len(rag_results)}
        except Exception as e:
            logger.error(f"问答失败: {e}")
            return {"answer": f"抱歉，回答生成失败: {e}", "source_type": "none"}


    async def stream_answer(self, question: str, summary: str, project_id: str):
        """Stream answer chunks for SSE"""
        import asyncio, json
        from backend.core.vector_store import get_vector_store
        from backend.utils.web_search import web_search
        
        yield {"type": "status", "text": "Thinking..."}
        
        try:
            # Get full answer
            answer = await self.run({
                "question": question,
                "summary": summary,
                "project_id": project_id,
            })
            full_text = answer.get("answer", "Sorry, I could not answer that.")
            
            # Stream text in chunks
            words = full_text.split()
            chunk_size = 5
            for i in range(0, len(words), chunk_size):
                chunk = " ".join(words[i:i+chunk_size])
                yield {"type": "chunk", "text": chunk + " "}
                await asyncio.sleep(0.05)
            
            yield {"type": "done", "source_type": answer.get("source_type", "summary")}
        except Exception as e:
            yield {"type": "error", "text": str(e)}
