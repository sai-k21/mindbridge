from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.database import Base
from app.encryption import EncryptedText

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    user_id = Column(String, index=True)
    role = Column(String)
    content = Column(EncryptedText)
    emotion = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class UserMemory(Base):
    __tablename__ = "user_memory"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, unique=True)
    summary = Column(EncryptedText)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class EmotionLog(Base):
    __tablename__ = "emotion_log"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    session_id = Column(String, index=True)
    emotion = Column(String)
    message_snippet = Column(EncryptedText)
    created_at = Column(DateTime, server_default=func.now())

class UserToken(Base):
    """
    A random secret issued the first time a user_id is seen. We store only
    a one-way hash of it — never the token itself — the same way a real
    system stores password hashes, not passwords. This means the raw token
    can only ever be handed to the client once, at creation time; the
    server has no way to produce it again after that, by design.
    """
    __tablename__ = "user_tokens"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, unique=True)
    token_hash = Column(String, unique=True)
    created_at = Column(DateTime, server_default=func.now())

class CrisisLog(Base):
    __tablename__ = "crisis_log"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    session_id = Column(String, index=True)
    message_snippet = Column(EncryptedText)
    response_given = Column(EncryptedText)
    escalated = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())