"""Tests for parent-child chunking"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.utils.chunking import ParentChildChunker, ChunkResult, ParentChunk, ChildChunk


class TestParentChildChunker:

    def test_empty_text(self):
        c = ParentChildChunker()
        result = c.chunk("")
        assert isinstance(result, ChunkResult)
        assert result.parents == []
        assert result.children == []

    def test_none_text(self):
        c = ParentChildChunker()
        result = c.chunk(None)
        assert isinstance(result, ChunkResult)
        assert result.parents == []
        assert result.children == []

    def test_short_text_single_chunk(self):
        c = ParentChildChunker(parent_size=1500, child_size=300)
        result = c.chunk("这是一段短文本。它只有一句话。")
        assert len(result.parents) == 1
        assert len(result.children) >= 1
        for child in result.children:
            assert child.parent_index == 0
            assert child.parent_text == result.parents[0].text

    def test_parent_child_linkage(self):
        c = ParentChildChunker(parent_size=500, child_size=150)
        paragraphs = [f"第{i}段内容。" * 20 for i in range(10)]
        text = "\n\n".join(paragraphs)
        result = c.chunk(text)

        assert len(result.parents) > 1, f"应生成多个父块，实际: {len(result.parents)}"
        assert len(result.children) > len(result.parents), "子块数应大于父块数"

        valid_indices = {p.index for p in result.parents}
        for child in result.children:
            assert child.parent_index in valid_indices
            assert child.parent_text == result.parents[child.parent_index].text

    def test_custom_sizes(self):
        c = ParentChildChunker(parent_size=800, child_size=200)
        text = "测试内容。" * 200
        result = c.chunk(text)
        for parent in result.parents:
            assert len(parent.text) <= 800 + 200

    def test_chunk_result_types(self):
        c = ParentChildChunker()
        result = c.chunk("测试。")
        assert isinstance(result, ChunkResult)
        assert all(isinstance(p, ParentChunk) for p in result.parents)
        assert all(isinstance(c, ChildChunk) for c in result.children)

    def test_single_paragraph(self):
        c = ParentChildChunker(parent_size=500, child_size=100)
        result = c.chunk("只有一段文字" * 30)
        assert len(result.parents) >= 1
