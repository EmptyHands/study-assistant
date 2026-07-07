"""父子块文档存储 — 编排 SQLite 父块 + Qdrant 子块向量"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import func
from qdrant_client.models import PointStruct

from backend.core.database import get_db_session
from backend.core.vector_store import get_vector_store
from backend.models.database import DocumentChunk
from backend.utils.chunking import ChunkResult

logger = logging.getLogger(__name__)


class DocumentStore:
    """父子块持久化 + 检索 + 过期管理"""

    def __init__(self):
        self.vector_store = get_vector_store()

    def index(self, project_id: str, result: ChunkResult) -> int:
        """持久化父子块：父块入 SQLite，子块入 Qdrant。返回父块数。

        先删除该项目的旧存储，再写入新数据（幂等重建）。
        """
        if not result.parents:
            return 0

        db = get_db_session()
        try:
            # 1. 清除旧数据
            db.query(DocumentChunk).filter(
                DocumentChunk.project_id == project_id
            ).delete()
            db.flush()

            # 2. 插入父块，获取 parent_id 映射
            parent_id_map = {}  # parent_index → UUID string
            for parent in result.parents:
                child_count = sum(
                    1 for c in result.children if c.parent_index == parent.index
                )
                doc = DocumentChunk(
                    project_id=project_id,
                    chunk_index=parent.index,
                    parent_text=parent.text,
                    child_count=child_count,
                )
                db.add(doc)
                db.flush()
                parent_id_map[parent.index] = doc.id

            db.commit()
            logger.info(
                "Saved %d parent chunks (project=%s)", len(result.parents), project_id
            )

        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        # 3. 子块向量写入 Qdrant
        self._index_children(project_id, result.children, parent_id_map)

        return len(result.parents)

    def _index_children(
        self,
        project_id: str,
        children: list,
        parent_id_map: dict,
    ):
        """将子块向量写入 Qdrant，携带 parent_id"""
        import asyncio

        points = []
        for i, child in enumerate(children):
            if not child.text or not child.text.strip():
                continue
            parent_id = parent_id_map.get(child.parent_index)
            if parent_id is None:
                continue
            embedding = asyncio.get_event_loop().run_until_complete(
                self.vector_store.embed_text(child.text)
            )
            point_id = self.vector_store.make_point_id(
                f"{project_id}_p{child.parent_index}_c{i}_{child.text[:50]}"
            )
            points.append(
                PointStruct(
                    id=point_id,
                    vector=embedding,
                    payload={
                        "project_id": project_id,
                        "chunk_index": i,
                        "text": child.text,
                        "parent_id": parent_id,
                    },
                )
            )

        if points:
            self.vector_store.client.upsert(
                collection_name=self.vector_store.collection_name,
                points=points,
            )
            logger.info(
                "Indexed %d child vectors (project=%s)", len(points), project_id
            )

    async def search(
        self, project_id: str, query: str, top_k: int = 5
    ) -> list[dict]:
        """检索：子块向量搜索 → 取父块 → 去重返回 → touch 续期。

        Returns:
            [{"parent_text": str, "score": float, "child_hits": int}, ...]
        """
        # 1. 向量检索子块
        child_results = await self.vector_store.search(project_id, query, top_k=top_k)

        if not child_results:
            return []

        # 2. 收集命中的 parent_id，按 parent_id 聚合
        parent_hits: dict[str, dict] = {}
        for r in child_results:
            pid = r.get("parent_id", "")
            if not pid:
                continue
            if pid not in parent_hits:
                parent_hits[pid] = {
                    "score": r["score"],
                    "child_hits": 0,
                }
            parent_hits[pid]["child_hits"] += 1
            parent_hits[pid]["score"] = max(parent_hits[pid]["score"], r["score"])

        if not parent_hits:
            return []

        # 3. 批量取父块文本
        db = get_db_session()
        try:
            parents = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.id.in_(list(parent_hits.keys())))
                .all()
            )
            result = []
            for p in parents:
                if p.id in parent_hits:
                    result.append(
                        {
                            "parent_text": p.parent_text,
                            "score": parent_hits[p.id]["score"],
                            "child_hits": parent_hits[p.id]["child_hits"],
                        }
                    )
            result.sort(key=lambda x: x["score"], reverse=True)

            # 4. 异步续期（不阻塞检索返回）
            try:
                self.touch(project_id)
            except Exception:
                logger.warning("touch failed for project=%s", project_id, exc_info=True)

            return result
        finally:
            db.close()

    def purge(self, project_id: str) -> bool:
        """手动删除项目所有父子块存储（SQLite + Qdrant）"""
        db = get_db_session()
        try:
            deleted = (
                db.query(DocumentChunk)
                .filter(DocumentChunk.project_id == project_id)
                .delete()
            )
            db.commit()
            logger.info("Purged %d parent chunks (project=%s)", deleted, project_id)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

        # 清理向量
        import asyncio
        try:
            asyncio.create_task(self.vector_store.delete_project(project_id))
        except Exception:
            pass

        return True

    def cleanup_expired(self, ttl_days: int = 14) -> int:
        """扫描 last_accessed_at 过期项目并清理。返回清理的项目数。"""
        cutoff = datetime.utcnow() - timedelta(days=ttl_days)
        db = get_db_session()
        try:
            rows = (
                db.query(DocumentChunk.project_id)
                .group_by(DocumentChunk.project_id)
                .having(func.max(DocumentChunk.last_accessed_at) < cutoff)
                .all()
            )
            expired_ids = [row[0] for row in rows]

            for pid in expired_ids:
                self.purge(pid)

            if expired_ids:
                logger.info(
                    "Cleaned up %d expired projects (ttl=%d days): %s",
                    len(expired_ids),
                    ttl_days,
                    expired_ids,
                )
            return len(expired_ids)
        finally:
            db.close()

    def touch(self, project_id: str) -> None:
        """更新项目下所有父块的 last_accessed_at"""
        db = get_db_session()
        try:
            db.query(DocumentChunk).filter(
                DocumentChunk.project_id == project_id
            ).update({"last_accessed_at": datetime.utcnow()})
            db.commit()
        except Exception:
            db.rollback()
        finally:
            db.close()


_store: Optional[DocumentStore] = None


def get_document_store() -> DocumentStore:
    global _store
    if _store is None:
        _store = DocumentStore()
    return _store
