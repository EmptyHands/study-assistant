"""Qdrant vector store - supports local / ollama / openai embedding backends"""
import logging
import hashlib
import asyncio
from typing import Optional
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct, Filter, FieldCondition, MatchValue
from .config import get_config, EmbeddingProvider

logger = logging.getLogger(__name__)

# common embedding dimensions
EMBEDDING_DIMS = {
    "all-MiniLM-L6-v2": 384,
    "all-mpnet-base-v2": 768,
    "bge-small-zh-v1.5": 512,
    "bge-large-zh-v1.5": 1024,
    "text-embedding-3-small": 1536,
    "text-embedding-3-large": 3072,
    "text-embedding-ada-002": 1536,
}


class VectorStore:
    def __init__(self):
        config = get_config()
        api_key = config.qdrant.api_key; self.client = QdrantClient(host=config.qdrant.host, port=config.qdrant.port, **({"api_key": api_key} if api_key else {}), https=False)
        self.collection_name = config.qdrant.collection_name
        self.embedding_provider = config.embedding.provider
        self.embedding_model_name = config.embedding.model_name
        self._local_model = None
        self._openai_client = None
        self._ollama_url = None
        self._init_embedding_backend(config)
        self._ensure_collection()

    def _init_embedding_backend(self, config):
        if self.embedding_provider == EmbeddingProvider.LOCAL:
            from sentence_transformers import SentenceTransformer
            device = config.embedding.local_device
            logger.info(f"Loading local embedding model: {self.embedding_model_name} on {device}")
            self._local_model = SentenceTransformer(self.embedding_model_name, device=device)
            self._embed_dim = self._local_model.get_sentence_embedding_dimension()
            logger.info(f"Local model loaded, dim={self._embed_dim}")
        elif self.embedding_provider == EmbeddingProvider.OLLAMA:
            import aiohttp
            self._ollama_url = (config.embedding.base_url or "http://localhost:11434").rstrip("/")
            self._ollama_session = None
            self._embed_dim = EMBEDDING_DIMS.get(self.embedding_model_name, 768)
            logger.info(f"Using Ollama embedding: {self.embedding_model_name}")
        else:
            from openai import AsyncOpenAI
            self._openai_client = AsyncOpenAI(
                api_key=config.embedding.api_key or config.llm.api_key,
                base_url=config.embedding.base_url or config.llm.base_url or "https://api.openai.com/v1",
            )
            self._embed_dim = EMBEDDING_DIMS.get(self.embedding_model_name, 1536)
            logger.info(f"Using OpenAI embedding: {self.embedding_model_name}")

    def _ensure_collection(self):
        dim = getattr(self, '_embed_dim', 1536)
        try:
            existing = self.client.get_collection(self.collection_name)
            existing_dim = existing.config.params.vectors.size
            if existing_dim != dim:
                # C1: 维度不匹配时显式报错，防止静默丢失全部向量数据
                raise ValueError(
                    f"嵌入向量维度不匹配: 已有 collection 为 {existing_dim}d, "
                    f"当前模型 {self.embedding_model_name} 为 {dim}d。\n"
                    f"请执行以下步骤完成迁移:\n"
                    f"  1. 手动删除旧 collection: client.delete_collection('{self.collection_name}')\n"
                    f"  2. 重启应用，将自动创建新 collection\n"
                    f"  3. 重新导入所有学习项目以重建向量索引"
                )
        except ValueError:
            raise
        except Exception:
            self.client.create_collection(
                collection_name=self.collection_name,
                vectors_config=VectorParams(size=dim, distance=Distance.COSINE),
            )
            logger.info(f"Created collection {self.collection_name} (dim={dim})")

    async def _embed(self, text: str) -> list[float]:
        if self.embedding_provider == EmbeddingProvider.LOCAL:
            return await asyncio.to_thread(self._local_model.encode, text, normalize_embeddings=True)
        elif self.embedding_provider == EmbeddingProvider.OLLAMA:
            import aiohttp
            if not getattr(self, '_ollama_session', None):
                self._ollama_session = aiohttp.ClientSession()
            async with self._ollama_session.post(
                f"{self._ollama_url}/api/embeddings",
                json={"model": self.embedding_model_name, "prompt": text}
            ) as resp:
                data = await resp.json()
                if "error" in data:
                    raise Exception(f"Ollama embedding error: {data['error']}")
                emb = data.get("embedding") or data.get("embeddings")
                if emb is None:
                    raise Exception(f"Unexpected Ollama response: {list(data.keys())}")
                return emb
        else:
            resp = await self._openai_client.embeddings.create(model=self.embedding_model_name, input=text)
            return resp.data[0].embedding

    async def add_documents(self, project_id: str, chunks: list[str], metadata: dict = None):
        if not chunks:
            return
        points = []
        for i, chunk in enumerate(chunks):
            if not chunk.strip():
                continue
            embedding = await self._embed(chunk)
            point_id = self._point_id(f"{project_id}_{i}_{chunk[:50]}")
            points.append(PointStruct(
                id=point_id, vector=embedding,
                payload={"project_id": project_id, "chunk_index": i, "text": chunk, **(metadata or {})}
            ))
        if points:
            self.client.upsert(collection_name=self.collection_name, points=points)
            logger.info(f"Added {len(points)} vectors (project={project_id})")

    async def search(self, project_id: str, query: str, top_k: int = 5) -> list[dict]:
        query_embedding = await self._embed(query)
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding,
            query_filter=Filter(must=[FieldCondition(key="project_id", match=MatchValue(value=project_id))]),
            limit=top_k, with_payload=True,
        )
        return [{"score": r.score, "text": r.payload.get("text", ""), "project_id": r.payload.get("project_id", "")} for r in results]

    async def delete_project(self, project_id: str):
        self.client.delete(
            collection_name=self.collection_name,
            points_selector=Filter(must=[FieldCondition(key="project_id", match=MatchValue(value=project_id))]),
        )

    def _point_id(self, text: str) -> str:
        return hashlib.md5(text.encode()).hexdigest()

    def close(self):
        self.client.close()
        if self.embedding_provider == EmbeddingProvider.OLLAMA and getattr(self, '_ollama_session', None):
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                loop.create_task(self._ollama_session.close())
            except Exception:
                pass


_store: Optional[VectorStore] = None


def get_vector_store() -> VectorStore:
    global _store
    if _store is None:
        _store = VectorStore()
    return _store
