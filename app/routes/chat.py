from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Conversation, UserMemory
import anthropic
import os

router = APIRouter()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

SYSTEM_PROMPT = """You are MindBridge, a compassionate AI companion 
for people dealing with workplace stress. You listen deeply, ask 
thoughtful questions, and gently challenge unhelpful thinking patterns. 
You never give hollow affirmations like 'you are amazing'. 
If someone seems to be in crisis, always refer them to 
professional help or the 988 crisis line (US)."""

@router.post("/chat")
def chat(user_id: str, session_id: str, message: str, db: Session = Depends(get_db)):

    # Save user message
    db.add(Conversation(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content=message
    ))
    db.commit()

    # Get current session history
    history = db.query(Conversation)\
        .filter(Conversation.session_id == session_id)\
        .order_by(Conversation.created_at)\
        .all()

    # Get long term memory for this user
    memory = db.query(UserMemory)\
        .filter(UserMemory.user_id == user_id)\
        .first()

    # Build system prompt with memory injected
    system = SYSTEM_PROMPT
    if memory:
        system += f"\n\nWhat you remember about this user from past sessions:\n{memory.summary}"

    # Build messages list
    messages = [{"role": h.role, "content": h.content} for h in history]

    # Call Claude
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1000,
        system=system,
        messages=messages
    )

    reply = response.content[0].text

    # Save assistant response
    db.add(Conversation(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content=reply
    ))
    db.commit()

    return {"session_id": session_id, "reply": reply}


@router.post("/memory/update")
def update_memory(user_id: str, db: Session = Depends(get_db)):

    # Get all conversations for this user
    all_convos = db.query(Conversation)\
        .filter(Conversation.user_id == user_id)\
        .order_by(Conversation.created_at)\
        .all()

    if not all_convos:
        return {"message": "No conversations found"}

    # Build full history text
    history_text = "\n".join([
        f"{c.role}: {c.content}" for c in all_convos
    ])

    # Ask Claude to summarize into memory
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""Summarize what you know about this user 
based on their conversations. Focus on: their main stressors, 
what helps them, recurring patterns, and anything important 
to remember for next time. Be concise and factual.

Conversations:
{history_text}"""
        }]
    )

    summary = response.content[0].text

    # Store or update memory
    memory = db.query(UserMemory)\
        .filter(UserMemory.user_id == user_id)\
        .first()

    if memory:
        memory.summary = summary
    else:
        db.add(UserMemory(user_id=user_id, summary=summary))

    db.commit()

    return {"user_id": user_id, "memory": summary}