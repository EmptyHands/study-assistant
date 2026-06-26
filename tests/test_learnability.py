"""Tests for learnability agent"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

@pytest.mark.asyncio
async def test_learnability_learnable():
    from backend.agents.learnability_agent import LearnabilityAgent
    agent = LearnabilityAgent()
    result = await agent.run({
        'raw_content': 'This is a textbook about Python programming. Chapter 1: Variables and Types.',
        'source_type': 'file'
    })
    assert 'is_learnable' in result
    assert 'reason' in result

@pytest.mark.asyncio
async def test_learnability_empty():
    from backend.agents.learnability_agent import LearnabilityAgent
    agent = LearnabilityAgent()
    result = await agent.run({'raw_content': '', 'source_type': 'file'})
    assert result['is_learnable'] is False

@pytest.mark.asyncio
async def test_learnability_not_learnable():
    from backend.agents.learnability_agent import LearnabilityAgent
    agent = LearnabilityAgent()
    result = await agent.run({
        'raw_content': 'Invoice #12345, Total: $99.99, Date: 2024-01-01',
        'source_type': 'file'
    })
    assert 'is_learnable' in result
