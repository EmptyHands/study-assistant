"""Tests for ActiveBuffer"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.utils.context.active_buffer import ActiveBuffer


class TestActiveBuffer:

    def test_empty_buffer_token_count(self):
        buf = ActiveBuffer(token_limit=4000)
        assert buf.token_count() == 0
        assert buf.remaining() == 4000

    def test_add_turn_increases_count(self):
        buf = ActiveBuffer(token_limit=4000)
        buf.add_turn("什么是量子力学？", "量子力学是研究微观粒子运动规律的物理学分支。")
        assert buf.token_count() > 0
        assert buf.remaining() < 4000

    def test_as_messages_format(self):
        buf = ActiveBuffer(token_limit=4000)
        buf.add_turn("问题1", "答案1")
        messages = buf.as_messages()
        assert len(messages) == 2
        assert messages[0] == {"role": "user", "content": "问题1"}
        assert messages[1] == {"role": "assistant", "content": "答案1"}

    def test_eviction_when_over_limit(self):
        buf = ActiveBuffer(token_limit=50, model_name="gpt-4o-mini")
        evicted = buf.add_turn("问题A" * 20, "答案A" * 20)
        assert evicted is None or len(evicted) == 0  # 第一条不驱逐

        evicted = buf.add_turn("问题B" * 20, "答案B" * 20)
        # 窗口超限，应该驱逐了第一部分
        assert evicted is not None
        assert len(evicted) > 0

    def test_keep_last_turn_protected(self):
        buf = ActiveBuffer(token_limit=30, model_name="gpt-4o-mini")
        buf.add_turn("Q1" * 20, "A1" * 20)
        evicted = buf.add_turn("Q2", "A2")
        # 最后一条 Q2/A2 不应被驱逐（保护最小值）
        messages = buf.as_messages()
        assert len(messages) >= 2  # 至少保留最后一轮

    def test_clear_resets_buffer(self):
        buf = ActiveBuffer(token_limit=4000)
        buf.add_turn("Q", "A")
        buf.clear()
        assert buf.token_count() == 0
        assert buf.as_messages() == []

    def test_model_fallback_encoding(self):
        # 未知模型降级为 cl100k_base
        buf = ActiveBuffer(token_limit=4000, model_name="unknown-model-xyz")
        buf.add_turn("Hello", "World")
        assert buf.token_count() > 0  # 不应崩溃
