import os
import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from app.main import app

# main.py requires X-API-Key on every route under chat.router — without
# this, every request below 403s before reaching any code under test,
# regardless of what that test is actually trying to check.
client = TestClient(app, headers={"X-API-Key": os.getenv("API_KEY")})


def test_root_endpoint():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "MindBridge is running"


def test_health_endpoint():
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert "status" in data
    assert "database" in data
    assert "redis" in data


def test_chat_empty_message():
    response = client.post("/api/v1/chat", json={
        "user_id": "test_user",
        "session_id": "test_session",
        "message": ""
    })
    assert response.status_code == 422


def test_chat_message_too_long():
    response = client.post("/api/v1/chat", json={
        "user_id": "test_user",
        "session_id": "test_session",
        "message": "a" * 2001
    })
    assert response.status_code == 422


def test_chat_missing_fields():
    response = client.post("/api/v1/chat", json={
        "user_id": "test_user"
    })
    assert response.status_code == 422


def test_chat_valid_message():
    # NOTE: must patch where the name is looked up (app.routes.chat), not
    # where it's defined (app.agent) — chat.py did `from app.agent import
    # mindbridge_graph`, which binds its own reference to the object at
    # import time. Patching app.agent's attribute doesn't touch that
    # already-bound name, so this used to silently call the real graph.
    with patch("app.routes.chat.mindbridge_graph") as mock_graph:
        mock_graph.invoke.return_value = {
            "emotion": "stressed",
            "reply": "I hear you. That sounds really difficult.",
            "crisis_escalated": False,
            "memory_summary": None
        }
        response = client.post("/api/v1/chat", json={
            "user_id": "test_user_123",
            "session_id": "test_session_123",
            "message": "I am stressed about work"
        })
        assert response.status_code == 200
        data = response.json()
        assert "reply" in data
        assert "emotion_detected" in data
        assert "crisis_escalated" in data
        assert "memory_active" in data


def test_memory_update_no_conversations():
    response = client.post(
        "/api/v1/memory/update?user_id=nonexistent_user_xyz",
        headers={"X-User-Id": "nonexistent_user_xyz"}
    )
    assert response.status_code == 404


def test_get_memory_not_found():
    response = client.get(
        "/api/v1/memory/nonexistent_user_xyz",
        headers={"X-User-Id": "nonexistent_user_xyz"}
    )
    assert response.status_code == 404


def test_get_history_not_found():
    response = client.get(
        "/api/v1/history/nonexistent_user_xyz",
        headers={"X-User-Id": "nonexistent_user_xyz"}
    )
    assert response.status_code == 404


def test_get_patterns_not_found():
    response = client.get(
        "/api/v1/patterns/nonexistent_user_xyz",
        headers={"X-User-Id": "nonexistent_user_xyz"}
    )
    assert response.status_code == 404