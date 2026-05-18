import pytest
from unittest.mock import patch, MagicMock
from app.routes.chat import detect_emotion, check_crisis_keywords


def test_crisis_keyword_detection():
    assert check_crisis_keywords("I want to kill myself") == True
    assert check_crisis_keywords("I want to die") == True
    assert check_crisis_keywords("I am stressed about work") == False
    assert check_crisis_keywords("I feel overwhelmed") == False


def test_crisis_keyword_case_insensitive():
    assert check_crisis_keywords("I WANT TO DIE") == True
    assert check_crisis_keywords("Kill Myself") == True


def test_emotion_detection_crisis_keyword():
    emotion = detect_emotion("I want to kill myself")
    assert emotion == "crisis"


def test_emotion_detection_valid_emotions():
    with patch("app.routes.chat.client") as mock_client:
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="stressed")]
        mock_client.messages.create.return_value = mock_response

        emotion = detect_emotion("I have too many deadlines")
        assert emotion in ["calm", "stressed", "anxious", "overwhelmed", "crisis"]

def test_emotion_detection_fallback():
    with patch("app.routes.chat.client") as mock_client:
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="unknown_emotion")]
        mock_client.messages.create.return_value = mock_response

        emotion = detect_emotion("some message")
        assert emotion == "stressed"