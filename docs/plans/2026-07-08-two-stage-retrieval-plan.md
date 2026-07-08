# 两阶段检索管线 — 实现计划

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 构建两阶段 RAG 检索管线：粗排（向量检索 top_k=20）→ 精排（Cross-Encoder 重排序）→ 输出 top 3-5 送入 LLM

**Architecture:** 新建 `retrieval.py` 作为检索编排层，串联 `DocumentStore.search()` 和 `Reranker.rerank()`。上层 QAAgent 只需将 `document_store.search(top_k=3)` 替换为 `pipeline.retrieve()` 一行改动。

**Tech Stack:** Python 3.10+, sentence-transformers (CrossEncoder), Qdrant, FastAPI

**Design doc:** `docs/plans/2026-07-08-two-stage-retrieval-design.md`

---

### Task 1: 扩展配置 — 新增重排序相关参数

**Files:**
- Modify: `backend/core/config.py:57-117`

**Step 1: 在 AppConfig dataclass 中新增 4 个字段**

在 `backend/core/config.py` 的 `AppConfig` 类中，于 `retrieval_top_k: int = 5` 之后（第 79 行附近）新增：

```python
# --- 两阶段检索 ---
coarse_top_k: int = 20
fine_top_k: int = 5
reranker_model: str = "BAAI/bge-reranker-v2-m3"
reranker_cache_dir: str = "E:/models"
```

**Step 2: 在 `__post_init__` 中添加环境变量读取**

在 `backend/core/config.py` 的 `__post_init__` 方法末尾（第 108 行附近，`self.agent_timeout` 之后）新增：

```python
self.coarse_top_k = int(os.getenv("COARSE_TOP_K", "20"))
self.fine_top_k = int(os.getenv("FINE_TOP_K", "5"))
self.reranker_model = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
self.reranker_cache_dir = os.getenv("RERANKER_CACHE_DIR", "E:/models")
```

**Step 3: 验证配置读取**

Run: `python -c "from backend.core.config import get_config; c = get_config(); print(f'coarse={c.coarse_top_k} fine={c.fine_top_k} model={c.reranker_model} cache={c.reranker_cache_dir}')"`
Expected: `coarse=20 fine=5 model=BAAI/bge-reranker-v2-m3 cache=E:/models`

**Step 4: Commit**

```bash
git add backend/core/config.py
git commit -m "feat: add reranker config fields (coarse_top_k, fine_top_k, reranker_model, reranker_cache_dir)"
```

---

### Task 2: 改造 Reranker — 支持自定义缓存目录

**Files:**
- Modify: `backend/utils/reranker.py`

**Step 1: 重写 reranker.py**

用以下内容替换 `backend/utils/reranker.py`：

```python
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
```

**Step 2: 验证 Reranker 基本功能**

Run: `python -c "from backend.utils.reranker import Reranker; r = Reranker(cache_dir='E:/models'); print('Reranker init OK')"`
Expected: `Reranker init OK`（模型延迟加载，此处不触发下载）

**Step 3: Commit**

```bash
git add backend/utils/reranker.py
git commit -m "feat: enhance reranker with lazy loading and cache_dir support"
```

---

### Task 3: 新建检索管线 — retrieval.py

**Files:**
- Create: `backend/core/retrieval.py`

**Step 1: 创建 retrieval.py**

新建 `backend/core/retrieval.py`，完整内容：

```python
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
```

**Step 2: 验证导入**

Run: `python -c "from backend.core.retrieval import RetrievalPipeline, get_retrieval_pipeline; print('Import OK')"`
Expected: `Import OK`

**Step 3: 验证单例**

Run: `python -c "from backend.core.retrieval import get_retrieval_pipeline; p1 = get_retrieval_pipeline(); p2 = get_retrieval_pipeline(); print('Singleton OK' if p1 is p2 else 'FAIL')"`
Expected: `Singleton OK`

**Step 4: Commit**

```bash
git add backend/core/retrieval.py
git commit -m "feat: add two-stage retrieval pipeline (coarse + rerank)"
```

---

### Task 4: 集成 QAAgent — 接入两阶段检索管线

**Files:**
- Modify: `backend/agents/qa_agent.py:40-46`（run 方法中的 RAG 检索）
- Modify: `backend/agents/qa_agent.py:113-120`（stream_answer 方法中的 RAG 检索）

**Step 1: 修改 run() 方法中的 RAG 检索调用**

在 `backend/agents/qa_agent.py` 的 `run()` 方法中（约第 40-46 行），将：

```python
        # 并行获取 RAG 和网络搜索结果
        rag_results = []
        try:
            from backend.core.document_store import get_document_store
            store = get_document_store()
            rag_results = await store.search(project_id, question, top_k=3)
        except Exception as e:
            logger.warning(f"RAG检索失败: {e}")
```

替换为：

```python
        # 并行获取 RAG（两阶段检索）和网络搜索结果
        rag_results = []
        try:
            from backend.core.retrieval import get_retrieval_pipeline
            pipeline = get_retrieval_pipeline()
            rag_results = await pipeline.retrieve(project_id, question)
        except Exception as e:
            logger.warning(f"RAG检索失败: {e}")
```

**Step 2: 修改 stream_answer() 方法中的 RAG 检索调用**

在 `backend/agents/qa_agent.py` 的 `stream_answer()` 方法中（约第 113-120 行），将：

```python
        rag_results = []
        try:
            from backend.core.document_store import get_document_store
            store = get_document_store()
            rag_results = await store.search(project_id, question, top_k=3)
        except Exception as e:
            logger.warning(f"RAG检索失败: {e}")
```

替换为：

```python
        rag_results = []
        try:
            from backend.core.retrieval import get_retrieval_pipeline
            pipeline = get_retrieval_pipeline()
            rag_results = await pipeline.retrieve(project_id, question)
        except Exception as e:
            logger.warning(f"RAG检索失败: {e}")
```

**注意：** 两处 RAG 结果的消费代码（`r.get("parent_text", "")`）保持不变，因为 `pipeline.retrieve()` 返回的 dict 结构兼容 `{"parent_text": str, "score": float}`。

**Step 3: 验证导入和语法**

Run: `python -c "from backend.agents.qa_agent import QAAgent; print('QAAgent import OK')"`
Expected: `QAAgent import OK`

**Step 4: Commit**

```bash
git add backend/agents/qa_agent.py
git commit -m "feat: integrate two-stage retrieval pipeline into QAAgent"
```

---

### Task 5: 更新 .env.example — 添加新配置项

**Files:**
- Modify: `.env.example`

**Step 1: 在 .env.example 末尾追加检索管线配置**

在 `.env.example` 文件末尾（第 45 行 `AGENT_TIMEOUT=300` 之后）新增：

```
# --- 两阶段检索 ---
# 粗排召回量（向量检索 top_k）
COARSE_TOP_K=20
# 精排后保留数（送入 LLM 的条数）
FINE_TOP_K=5
# Cross-Encoder 重排序模型
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
# 模型缓存目录
RERANKER_CACHE_DIR=E:/models
```

**Step 2: Commit**

```bash
git add .env.example
git commit -m "chore: add two-stage retrieval config to .env.example"
```

---

### Task 6: 端到端验证

**Step 1: 验证整体管线**

Run: `python -c "
from backend.core.config import get_config
from backend.core.retrieval import RetrievalPipeline
import asyncio

async def main():
    c = get_config()
    print(f'Config: coarse={c.coarse_top_k}, fine={c.fine_top_k}')
    print(f'Reranker: {c.reranker_model} @ {c.reranker_cache_dir}')
    print('Pipeline structure OK')

asyncio.run(main())
"`
Expected:
```
Config: coarse=20, fine=5
Reranker: BAAI/bge-reranker-v2-m3 @ E:/models
Pipeline structure OK
```

**Step 2: 确认改动范围**

Run: `git diff --name-only HEAD~4`
Expected: 只包含以下文件：
```
backend/core/config.py
backend/utils/reranker.py
backend/core/retrieval.py
backend/agents/qa_agent.py
.env.example
```

---

## 改动总览

| 文件 | 改动 | 行数 |
|------|------|------|
| `backend/core/config.py` | +8 行（4 字段 + 4 env 读取） | ~10 |
| `backend/utils/reranker.py` | 重写（加 lazy loading, cache_dir, logging） | ~70 |
| `backend/core/retrieval.py` | **新建**（管线编排） | ~110 |
| `backend/agents/qa_agent.py` | 改 4 行（2 处 import + 2 处调用） | ~8 |
| `.env.example` | +5 行 | ~5 |

**不改动：** `document_store.py`, `vector_store.py`, `chunking.py`, `qa_service.py`, `llm_adapter.py`, `scheduler.py`

## 风险与注意事项

1. **模型下载**：`bge-reranker-v2-m3` 约 2.3GB，首次加载时需确保 E 盘空间充足且网络通畅
2. **推理延迟**：Cross-Encoder 对 20 条文档逐一打分，预计耗时 1-3 秒（CPU）/ 0.1-0.5 秒（GPU）
3. **依赖确认**：`sentence-transformers` 已在 `requirements.txt` 中，无需额外安装
4. **版本兼容**：当前 `sentence_transformers` 的 `CrossEncoder` 支持 `cache_dir` 参数（v2.2.0+）
