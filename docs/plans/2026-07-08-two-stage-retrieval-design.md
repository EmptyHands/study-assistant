# 两阶段检索管线 — 设计文档

**日期:** 2026-07-08
**状态:** 已确认
**分支:** master

---

## 1. 背景与动机

当前 RAG 检索流程过于简陋：向量检索直接取 `top_k=3` 送入 LLM，没有重排序环节。存在两个问题：

- **召回量太小**：top_k=3 容易遗漏相关文档，尤其当向量相似度不能精确反映语义相关性时
- **无精排环节**：向量相似度（余弦距离）是粗粒度的，Cross-Encoder 能更准确地判断 [query, document] 的语义相关性

## 2. 设计方案

### 2.1 两阶段流水线

```
用户问题
  │
  ▼
┌──────────────────────────────────────┐
│  RetrievalPipeline.retrieve()        │
│                                      │
│  阶段一：粗排（召回阶段）              │
│  ├─ DocumentStore.search(top_k=20)   │
│  └─ 目标：高召回率，宁可多捞，不能漏   │
│                                      │
│  阶段二：精排（重排序阶段）            │
│  ├─ Reranker.rerank(candidates)      │
│  ├─ Cross-Encoder 逐对打分            │
│  └─ 取 top 3-5 送入 LLM              │
└──────────────────────────────────────┘
  │
  ▼
QAAgent 拼 prompt → LLM 生成回答
```

### 2.2 模块职责

| 模块 | 文件 | 职责 |
|------|------|------|
| 检索管线 | `backend/core/retrieval.py`（新建） | 编排粗排→精排流程，对上层暴露统一接口 |
| 重排序器 | `backend/utils/reranker.py`（改造） | Cross-Encoder 模型加载与推理 |
| 文档存储 | `backend/core/document_store.py`（不改） | 父子块向量检索，作为粗排数据源 |
| 向量存储 | `backend/core/vector_store.py`（不改） | Qdrant 底层向量操作 |

### 2.3 核心接口

```python
# backend/core/retrieval.py

class RetrievalPipeline:
    def __init__(self):
        self.document_store = get_document_store()
        self.reranker = Reranker(
            model_name=config.reranker_model,
            cache_dir=config.reranker_cache_dir,
        )

    async def retrieve(
        self,
        project_id: str,
        query: str,
        coarse_top_k: int = 20,
        fine_top_k: int = 5,
    ) -> list[dict]:
        """两阶段检索
        Returns:
            [{"parent_text": str, "score": float}, ...]
        """
        # 阶段一：粗排
        candidates = await self.document_store.search(
            project_id, query, top_k=coarse_top_k
        )
        if not candidates:
            return []

        # 阶段二：精排
        try:
            documents = [c["parent_text"] for c in candidates]
            ranked = self.reranker.rerank(query, documents)
            return [
                {"parent_text": doc, "score": score}
                for doc, score in ranked[:fine_top_k]
            ]
        except Exception:
            # fail-open: 精排失败时按向量分数截断
            logger.warning("Rerank failed, falling back to vector scores")
            candidates.sort(key=lambda x: x["score"], reverse=True)
            return [
                {"parent_text": c["parent_text"], "score": c["score"]}
                for c in candidates[:fine_top_k]
            ]


# backend/utils/reranker.py

class Reranker:
    def __init__(
        self,
        model_name: str = "BAAI/bge-reranker-v2-m3",
        cache_dir: str = "E:/models",
    ):
        from sentence_transformers import CrossEncoder
        self.model = CrossEncoder(model_name, cache_dir=cache_dir)

    def rerank(self, query: str, documents: list[str]) -> list[tuple[str, float]]:
        """对候选文档重排序，返回 (document, score) 列表，按分数降序"""
        pairs = [[query, doc] for doc in documents]
        scores = self.model.predict(pairs)
        ranked = sorted(zip(documents, scores), key=lambda x: x[1], reverse=True)
        return ranked
```

## 3. 配置

在 `AppConfig` 中新增：

```python
# backend/core/config.py
coarse_top_k: int = 20
fine_top_k: int = 5
reranker_model: str = "BAAI/bge-reranker-v2-m3"
reranker_cache_dir: str = "E:/models"
```

对应环境变量（可选覆盖）：
```
COARSE_TOP_K=20
FINE_TOP_K=5
RERANKER_MODEL=BAAI/bge-reranker-v2-m3
RERANKER_CACHE_DIR=E:/models
```

## 4. 容错策略（Fail-Open）

| 环节 | 异常处理 |
|------|---------|
| 粗排（DocumentStore） | 已在 QAAgent 中 try/except，失败返回空列表 |
| 精排（Reranker） | try/except，失败时 fallback 到向量分数排序截断 |
| 模型首次加载 | CrossEncoder 自动从 HuggingFace 下载到 cache_dir |

## 5. 改动范围

| 文件 | 改动类型 | 说明 |
|------|---------|------|
| `backend/core/retrieval.py` | **新建** | 检索管线编排 |
| `backend/utils/reranker.py` | **改造** | 加 cache_dir、完善接口、加注释 |
| `backend/core/config.py` | 修改 | 新增 4 个配置项 + 环境变量读取 |
| `backend/agents/qa_agent.py` | 修改 | `run()` 和 `stream_answer()` 改用 pipeline.retrieve() |
| `.env.example` | 修改 | 新增可选配置项 |

**不改动的文件：** `document_store.py`, `vector_store.py`, `chunking.py`, `qa_service.py`, `llm_adapter.py`

## 6. 可扩展性

后续迭代只需在 `retrieval.py` 中扩展，无需修改下游：

| 扩展方向 | 入口点 |
|---------|--------|
| 混合检索（dense + BM25） | `retrieve()` 的粗排阶段增加 BM25 源 |
| 查询改写 | `retrieve()` 入口增加 `_expand_query()` |
| 多路召回融合 | `retrieve()` 支持并行多 collection |
| MMR 去重 | `retrieve()` 的截断阶段增加多样性算法 |

## 7. 确认记录

- Reranker 部署方式：本地 `sentence_transformers`（非 Ollama）
- 模型缓存目录：`E:/models`
- 管线位置：独立模块 `retrieval.py`
- 命名原则：通用、可扩展
