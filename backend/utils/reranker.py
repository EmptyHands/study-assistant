"""Cross-Encoder 重排序器 — 对候选文档进行语义相关性精排"""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class Reranker:
    """基于 Cross-Encoder 的文档重排序器。

    Cross-Encoder 将 [query, document] 拼接后送入 BERT 模型，
    输出一个相关性分数，比向量余弦相似度更精准。

    使用示例:
        reranker = Reranker(cache_dir="E:/models")
        ranked = reranker.rerank("什么是机器学习", ["文档A", "文档B", "文档C"])
        # => [("文档B", 0.92), ("文档A", 0.75), ("文档C", 0.31)]
    """

    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        cache_dir: str = "E:/models",
    ):
        self.model_name = model_name
        self.cache_dir = cache_dir
        self._model: Optional[object] = None

    @property
    def model(self):
        """延迟加载模型，首次调用时自动从 HuggingFace 下载到 cache_dir"""
        if self._model is None:
            from sentence_transformers import CrossEncoder
            logger.info(
                "Loading reranker model: %s (cache_dir=%s)",
                self.model_name,
                self.cache_dir,
            )
            self._model = CrossEncoder(
                self.model_name,
                cache_dir=self.cache_dir,
            )
            logger.info("Reranker model loaded")
        return self._model

    def rerank(
        self, query: str, documents: list[str]
    ) -> list[tuple[str, float]]:
        """对候选文档列表进行重排序。

        Args:
            query: 用户查询
            documents: 候选文档文本列表

        Returns:
            [(document_text, score), ...] 按分数降序排列。
            score 范围取决于模型，bge-reranker-v2-m3 通常在 0~1 之间。
        """
        if not documents:
            return []

        pairs = [[query, doc] for doc in documents]
        scores = self.model.predict(pairs)

        # predict 可能返回单个 float（单文档时）
        if not hasattr(scores, '__iter__'):
            scores = [scores]

        ranked = sorted(
            zip(documents, scores), key=lambda x: x[1], reverse=True
        )
        return ranked
