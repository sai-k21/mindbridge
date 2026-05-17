from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean
from sqlalchemy.sql import func
from app.database import Base

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, index=True)
    user_id = Column(String, index=True)
    role = Column(String)
    content = Column(Text)
    emotion = Column(String, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

class UserMemory(Base):
    __tablename__ = "user_memory"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True, unique=True)
    summary = Column(Text)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

class EmotionLog(Base):
    __tablename__ = "emotion_log"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    session_id = Column(String, index=True)
    emotion = Column(String)
    message_snippet = Column(Text)
    created_at = Column(DateTime, server_default=func.now())

class CrisisLog(Base):
    __tablename__ = "crisis_log"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(String, index=True)
    session_id = Column(String, index=True)
    message_snippet = Column(Text)
    response_given = Column(Text)
    escalated = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())