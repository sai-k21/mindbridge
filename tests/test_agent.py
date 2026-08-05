import pytest
from unittest.mock import patch, MagicMock
from app.routes.chat import check_crisis_keywords
from app.agent import emotion_agent


def _state(message: str) -> dict:
    """Minimal AgentState for testing emotion_agent in isolation."""
    return {
        "user_id": "test-user",
        "session_id": "test-session",
        "message": message,
        "emotion": None,
        "memory_summary": None,
        "conversation_history": None,
        "reply": None,
        "crisis_escalated": False,
        "db": None,
    }


def test_crisis_keyword_detection():
    assert check_crisis_keywords("I want to kill myself") == True
    assert check_crisis_keywords("I want to die") == True
    assert check_crisis_keywords("I am stressed about work") == False
    assert check_crisis_keywords("I feel overwhelmed") == False


def test_crisis_keyword_case_insensitive():
    assert check_crisis_keywords("I WANT TO DIE") == True
    assert check_crisis_keywords("Kill Myself") == True


def test_emotion_agent_crisis_keyword_bypasses_llm():
    # This is the actual production safety path — no API key or network
    # needed, since the rule-based check must short-circuit before any
    # LLM call is made.
    result = emotion_agent(_state("I want to kill myself"))
    assert result["emotion"] == "crisis"


def test_emotion_agent_uses_haiku_for_classification():
    # Regression test: emotion classification should use Haiku, not a
    # larger/more expensive model — this call runs on every message.
    with patch("app.agent.client") as mock_client:
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="stressed")]
        mock_client.messages.create.return_value = mock_response

        result = emotion_agent(_state("I have too many deadlines"))

        assert result["emotion"] == "stressed"
        _, kwargs = mock_client.messages.create.call_args
        assert kwargs["model"] == "claude-haiku-4-5-20251001"


def test_emotion_agent_fallback_on_unexpected_output():
    with patch("app.agent.client") as mock_client:
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="unknown_emotion")]
        mock_client.messages.create.return_value = mock_response

        result = emotion_agent(_state("some message"))
        assert result["emotion"] == "stressed"