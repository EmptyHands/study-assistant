"""Tests for DocumentStore"""
import pytest
import sys, os, uuid
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ['LLM_API_KEY'] = 'test-key'
os.environ['DATABASE_URL'] = 'sqlite:///./data/test.db'

from backend.core.document_store import DocumentStore, get_document_store
from backend.utils.chunking import ChunkResult, ParentChunk, ChildChunk


@pytest.fixture
def sample_chunk_result():
    parents = [
        ParentChunk(index=0, text="第一段父块内容。" * 20),
        ParentChunk(index=1, text="第二段父块内容。" * 20),
    ]
    children = [
        ChildChunk(text="第一段子块1", parent_index=0, parent_text=parents[0].text),
        ChildChunk(text="第一段子块2", parent_index=0, parent_text=parents[0].text),
        ChildChunk(text="第二段子块1", parent_index=1, parent_text=parents[1].text),
    ]
    return ChunkResult(parents=parents, children=children)


class TestDocumentStore:

    @pytest.mark.asyncio
    async def test_index_and_purge(self, sample_chunk_result):
        project_id = str(uuid.uuid4())
        store = get_document_store()
        count = await store.index(project_id, sample_chunk_result)
        assert count == 2
        result = store.purge(project_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_index_empty_result(self):
        store = get_document_store()
        count = await store.index(str(uuid.uuid4()), ChunkResult())
        assert count == 0

    @pytest.mark.asyncio
    async def test_touch_does_not_raise(self, sample_chunk_result):
        project_id = str(uuid.uuid4())
        store = get_document_store()
        await store.index(project_id, sample_chunk_result)
        store.touch(project_id)
        store.purge(project_id)

    def test_cleanup_expired_returns_zero_for_future_ttl(self):
        store = get_document_store()
        count = store.cleanup_expired(ttl_days=36500)
        assert count == 0

    def test_get_document_store_singleton(self):
        s1 = get_document_store()
        s2 = get_document_store()
        assert s1 is s2
