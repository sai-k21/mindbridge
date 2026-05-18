from pydantic import BaseModel, field_validator, Field

class ChatRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=50)
    session_id: str = Field(..., min_length=1, max_length=100)
    message: str = Field(..., min_length=1, max_length=2000)

    @field_validator("message")
    @classmethod
    def message_not_empty(cls, v):
        if not v.strip():
            raise ValueError("Message cannot be empty or whitespace")
        return v.strip()

    @field_validator("user_id")
    @classmethod
    def user_id_clean(cls, v):
        if not v.strip():
            raise ValueError("user_id cannot be empty")
        return v.strip()

class MemoryRequest(BaseModel):
    user_id: str = Field(..., min_length=1, max_length=50)

class ChatResponse(BaseModel):
    session_id: str
    reply: str
    emotion_detected: str
    crisis_escalated: bool
    memory_active: bool