"""Tests for ConversationContext"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.utils.context.conversation_context import ConversationContext


class TestConversationContext:

    def test_init_creates_buffer(self):
        ctx = ConversationContext(project_id="test-ctx-1")
        assert ctx.buffer is not None
        assert ctx.store is not None
        assert ctx.project_id == "test-ctx-1"

    def test_add_turn_no_summary_needed(self):
        """添加少量对话不触发摘要"""
        ctx = ConversationContext(project_id="test-ctx-2", token_limit=4000)
        ctx.add_turn("Hello", "Hi there!")
        assert ctx.buffer.token_count() > 0

    def test_build_chat_history_empty(self):
        ctx = ConversationContext(project_id="test-ctx-3")
        history = ctx.build_chat_history()
        assert history == []

    def test_build_chat_history_with_turns(self):
        ctx = ConversationContext(project_id="test-ctx-4")
        ctx.add_turn("Q1", "A1")
        ctx.add_turn("Q2", "A2")
        history = ctx.build_chat_history()
        assert len(history) == 4
        assert history[0] == {"role": "user", "content": "Q1"}
        assert history[-1] == {"role": "assistant", "content": "A2"}

    def test_build_system_prompt_addition_empty(self):
        ctx = ConversationContext(project_id="test-ctx-5")
        addition = ctx.build_system_prompt_addition()
        assert addition == ""

    def test_custom_token_limit(self):
        ctx = ConversationContext(project_id="test-ctx-6", token_limit=30)
        ctx.add_turn("A" * 100, "B" * 100)
        history = ctx.build_chat_history()
        total_chars = sum(len(m["content"]) for m in history)
        assert total_chars < 500
