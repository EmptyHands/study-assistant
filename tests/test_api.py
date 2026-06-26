"""Tests for API endpoints"""
import pytest
from fastapi.testclient import TestClient
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
os.environ['LLM_API_KEY'] = 'test-key'
os.environ['DATABASE_URL'] = 'sqlite:///./data/test.db'

from backend.main import app
client = TestClient(app)

def test_health():
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json()['status'] == 'healthy'

def test_list_projects_empty():
    response = client.get('/api/v1/projects')
    assert response.status_code == 200
    assert 'projects' in response.json()

def test_docs_available():
    response = client.get('/docs')
    assert response.status_code == 200
