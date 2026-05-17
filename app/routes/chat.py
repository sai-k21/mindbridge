from fastapi import APIRouter, Depends, HTTPException
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

    # Build system prompt — inject memory if it exists
    system = SYSTEM_PROMPT
    if memory and memory.summary:
        system += f"\n\nWhat you remember about this user from past sessions:\n{memory.summary}"
        system += "\n\nUse this memory naturally — don't announce that you remember things, just use the context."

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

    return {
        "session_id": session_id,
        "reply": reply,
        "memory_active": memory is not None
    }


@router.post("/memory/update")
def update_memory(user_id: str, db: Session = Depends(get_db)):

    # Get all conversations for this user
    all_convos = db.query(Conversation)\
        .filter(Conversation.user_id == user_id)\
        .order_by(Conversation.created_at)\
        .all()

    if not all_convos:
        raise HTTPException(status_code=404, detail="No conversations found for this user")

    # Build full history text
    history_text = "\n".join([
        f"{c.role}: {c.content}" for c in all_convos
    ])

    # Ask Claude to summarize into memory
    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": f"""You are building a memory profile for an AI companion.
Summarize what you know about this user based on their conversations.

Focus on:
- Their main stressors and triggers
- What has helped them in the past
- Recurring themes or patterns
- Their communication style and preferences
- Anything important to remember for next time

Be concise, factual, and compassionate. Write in second person (e.g. "You tend to...").

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

    return {
        "user_id": user_id,
        "memory": summary,
        "message": "Memory updated successfully"
    }


@router.get("/memory/{user_id}")
def get_memory(user_id: str, db: Session = Depends(get_db)):

    memory = db.query(UserMemory)\
        .filter(UserMemory.user_id == user_id)\
        .first()

    if not memory:
        raise HTTPException(status_code=404, detail="No memory found for this user")

    return {
        "user_id": user_id,
        "memory": memory.summary,
        "updated_at": memory.updated_at
    }


@router.get("/history/{user_id}")
def get_history(user_id: str, db: Session = Depends(get_db)):

    conversations = db.query(Conversation)\
        .filter(Conversation.user_id == user_id)\
        .order_by(Conversation.created_at)\
        .all()

    if not conversations:
        raise HTTPException(status_code=404, detail="No conversations found for this user")

    return {
        "user_id": user_id,
        "total_messages": len(conversations),
        "conversations": [
            {
                "session_id": c.session_id,
                "role": c.role,
                "content": c.content,
                "created_at": str(c.created_at)
            }
            for c in conversations
        ]
    }