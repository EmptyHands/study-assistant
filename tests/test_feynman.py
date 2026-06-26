"""Tests for Feynman agent"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

@pytest.mark.asyncio
async def test_generate_question():
    from backend.agents.feynman_agent import FeynmanAgent
    agent = FeynmanAgent()
    result = await agent.generate_question({
        'title': 'Bubble Sort',
        'framework': {'key_concepts': ['comparison', 'swap', 'O(n^2)']},
        'key_concepts': ['comparison', 'swap', 'O(n^2)'],
        'history': []
    })
    assert 'question' in result
    assert len(result['question']) > 0

@pytest.mark.asyncio
async def test_evaluate_answer():
    from backend.agents.feynman_agent import FeynmanAgent
    agent = FeynmanAgent()
    result = await agent.evaluate_answer({
        'title': 'Bubble Sort',
        'question': 'Can you explain what bubble sort is?',
        'answer': 'Bubble sort compares adjacent elements and swaps them if they are in the wrong order.'
    })
    assert 'understanding_level' in result
    assert result['understanding_level'] in ('good', 'partial', 'poor')
