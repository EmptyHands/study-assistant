"""检索管线 — 两阶段检索编排（粗排 → 精排）

可扩展点:
    - 混合检索: 在 coarse_retrieve 阶段增加 BM25 源
    - 查询改写: 在 retrieve() 入口增加 _expand_query()
    - MMR 去重: 在截断阶段增加多样性算法
"""
import logging
from typing import Optional

from backend.core.config import get_config
from backend.core.document_store import get_document_store
from backend.utils.reranker import Reranker

logger = logging.getLogger(__name__)


class RetrievalPipeline:
    """两阶段检索管线。

    阶段一（粗排）：向量检索取 top_k=20，目标高召回率
    阶段二（精排）：Cross-Encoder 对候选文档逐对打分，取 top 3-5

    容错策略（fail-open）：
        - 粗排失败：返回空列表
        - 精排失败：fallback 到向量分数排序截断
    """

    def __init__(self):
        config = get_config()
        self.document_store = get_document_store()
        self.reranker = Reranker(
            model_name=config.reranker_model,
            cache_dir=config.reranker_cache_dir,
        )
        self.coarse_top_k = config.coarse_top_k
        self.fine_top_k = config.fine_top_k

    async def retrieve(
        self,
        project_id: str,
        query: str,
        coarse_top_k: Optional[int] = None,
        fine_top_k: Optional[int] = None,
    ) -> list[dict]:
        """执行两阶段检索。

        Args:
            project_id: 项目 ID
            query: 用户查询
            coarse_top_k: 粗排召回量，默认取配置值 20
            fine_top_k: 精排后保留数，默认取配置值 5

        Returns:
            [{"parent_text": str, "score": float}, ...]
            按 Cross-Encoder 相关性分数降序排列
        """
        coarse_k = coarse_top_k if coarse_top_k is not None else self.coarse_top_k
        fine_k = fine_top_k if fine_top_k is not None else self.fine_top_k

        # 阶段一：粗排（向量检索）
        candidates = await self.document_store.search(
            project_id, query, top_k=coarse_k
        )

        if not candidates:
            logger.debug("No candidates from coarse retrieval for project=%s", project_id)
            return []

        logger.debug(
            "Coarse retrieval returned %d candidates (project=%s)",
            len(candidates), project_id,
        )

        # 阶段二：精排（Cross-Encoder 重排序）
        try:
            documents = [c["parent_text"] for c in candidates]
            ranked = self.reranker.rerank(query, documents)
            result = [
                {"parent_text": doc, "score": float(score)}
                for doc, score in ranked[:fine_k]
            ]
            logger.debug(
                "Reranked from %d to %d results (project=%s)",
                len(candidates), len(result), project_id,
            )
            return result

        except Exception:
            # fail-open: 精排失败时按向量分数降序截断
            logger.warning(
                "Rerank failed for project=%s, falling back to vector scores",
                project_id, exc_info=True,
            )
            candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
            return [
                {"parent_text": c["parent_text"], "score": c.get("score", 0)}
                for c in candidates[:fine_k]
            ]


_pipeline: Optional[RetrievalPipeline] = None


def get_retrieval_pipeline() -> RetrievalPipeline:
    """获取检索管线单例"""
    global _pipeline
    if _pipeline is None:
        _pipeline = RetrievalPipeline()
    return _pipeline
