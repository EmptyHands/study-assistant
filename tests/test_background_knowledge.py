"""Tests for BackgroundKnowledge"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from backend.utils.context.background_knowledge import BackgroundKnowledge, BackgroundKnowledgeStore


class TestBackgroundKnowledge:

    def test_empty_knowledge_format(self):
        bk = BackgroundKnowledge()
        store = BackgroundKnowledgeStore(project_id="test-project")
        formatted = store.format_for_prompt(bk)
        assert formatted == ""

    def test_partial_knowledge_format(self):
        bk = BackgroundKnowledge(
            user_intents="理解量子力学",
            key_facts="薛定谔方程是基础",
        )
        store = BackgroundKnowledgeStore(project_id="test-project")
        formatted = store.format_for_prompt(bk)
        assert "理解量子力学" in formatted
        assert "薛定谔方程是基础" in formatted
        assert "## 对话历史背景" in formatted

    def test_full_knowledge_format(self):
        bk = BackgroundKnowledge(
            user_intents="用户想学微积分",
            assistant_actions="助手讲解了导数的定义和几何意义",
            key_facts="用户已掌握极限概念",
            message_count=5,
        )
        store = BackgroundKnowledgeStore(project_id="test-project")
        formatted = store.format_for_prompt(bk)
        assert "用户想学微积分" in formatted
        assert "助手讲解了导数的定义和几何意义" in formatted
        assert "用户已掌握极限概念" in formatted

    def test_format_differs_when_empty_vs_populated(self):
        store = BackgroundKnowledgeStore(project_id="test-project")
        empty = store.format_for_prompt(BackgroundKnowledge())
        full = store.format_for_prompt(BackgroundKnowledge(
            user_intents="test", assistant_actions="test", key_facts="test"
        ))
        assert empty != full
        assert len(full) > len(empty)
