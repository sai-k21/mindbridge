from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Conversation, UserMemory, EmotionLog, CrisisLog, UserToken
from app.agent import mindbridge_graph
from app.schemas import ChatRequest
from app.cache import invalidate_memory_cache, check_and_increment_daily_usage
from slowapi import Limiter
from slowapi.util import get_remote_address
from fastapi import Header


import anthropic
import os
import secrets


def get_real_client_ip(request: Request) -> str:
    """
    Requests arrive via the Vercel proxy, so request.client.host is Vercel's
    IP for every visitor. The proxy forwards the real visitor IP in
    X-Forwarded-For — prefer that so rate limiting is actually per-visitor.
    """
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return get_remote_address(request)


limiter = Limiter(key_func=get_real_client_ip)

router = APIRouter(prefix="/v1")
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Crisis keywords for fast rule-based detection
CRISIS_KEYWORDS = [
    "kill myself", "want to die", "end my life", "suicide", "suicidal",
    "don't want to exist", "better off dead", "no reason to live",
    "can't go on", "give up on life", "hurt myself", "self harm"
]

def get_or_create_access_token(user_id: str, db: Session) -> str:
    """
    Called from /chat on every message. Cheap (one indexed lookup) and
    idempotent — returns the existing token if this user_id has one,
    otherwise mints a new one. The frontend stores whatever it gets back.
    """
    record = db.query(UserToken).filter(UserToken.user_id == user_id).first()
    if record:
        return record.token

    token = secrets.token_urlsafe(32)
    db.add(UserToken(user_id=user_id, token=token))
    db.commit()
    return token


def verify_access_token(
    user_id: str,
    x_access_token: str = Header(...),
    db: Session = Depends(get_db),
):
    """
    Proves the caller actually owns this user_id — the earlier design just
    checked that a client-supplied X-User-Id header matched the user_id in
    the URL, which anyone could satisfy by declaring whatever they wanted.
    This checks a secret token that only the real owner would have been
    given, using a constant-time comparison to avoid timing attacks.
    """
    record = db.query(UserToken).filter(UserToken.user_id == user_id).first()
    if not record or not secrets.compare_digest(record.token, x_access_token):
        raise HTTPException(status_code=403, detail="Forbidden")


def check_crisis_keywords(message: str) -> bool:
    """
    Free, zero-latency pre-check used to make sure the daily budget guard
    (below) can never delay or block a message that might be a crisis —
    the real crisis path in agent.py runs this same check independently
    and costs no LLM call either way.
    """
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in CRISIS_KEYWORDS)


@router.post("/chat")
@limiter.limit("10/minute")
def chat(request: Request, chat_request: ChatRequest, db: Session = Depends(get_db)):
    user_id = chat_request.user_id
    session_id = chat_request.session_id
    message = chat_request.message

    # Daily budget guard — protects the demo's Claude spend from abuse.
    # Crisis messages ALWAYS bypass this: the keyword check is free and the
    # crisis path itself makes zero LLM calls, so there's no cost reason to
    # ever gate it, and every reason not to withhold a safety response.
    if not check_crisis_keywords(message) and not check_and_increment_daily_usage():
        return {
            "session_id": session_id,
            "reply": (
                "MindBridge's free demo has reached its message limit for "
                "today — thanks for trying it out! Please check back "
                "tomorrow, or reach out directly if you'd like to see more "
                "of the project."
            ),
            "emotion_detected": "calm",
            "crisis_escalated": False,
            "memory_active": False
        }

    # Save user message first
    db.add(Conversation(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content=message
    ))
    db.commit()

    access_token = get_or_create_access_token(user_id, db)

    # Run through LangGraph multi-agent pipeline
    result = mindbridge_graph.invoke({
        "user_id": user_id,
        "session_id": session_id,
        "message": message,
        "emotion": None,
        "memory_summary": None,
        "conversation_history": None,
        "reply": None,
        "crisis_escalated": False,
        "db": db
    })

    emotion = result["emotion"]
    reply = result["reply"]
    crisis_escalated = result["crisis_escalated"]

    # Log emotion
    db.add(EmotionLog(
        user_id=user_id,
        session_id=session_id,
        emotion=emotion,
        message_snippet=message[:100]
    ))

    # Log crisis if triggered
    if crisis_escalated:
        db.add(CrisisLog(
            user_id=user_id,
            session_id=session_id,
            message_snippet=message[:200],
            response_given=reply,
            escalated=True
        ))

    # Save assistant response
    db.add(Conversation(
        user_id=user_id,
        session_id=session_id,
        role="assistant",
        content=reply,
        emotion=emotion
    ))
    db.commit()

    return {
        "session_id": session_id,
        "reply": reply,
        "emotion_detected": emotion,
        "crisis_escalated": crisis_escalated,
        "memory_active": result["memory_summary"] is not None,
        "access_token": access_token
    }

@router.post("/memory/update")
def update_memory(user_id: str, db: Session = Depends(get_db), _: None = Depends(verify_access_token)):

    all_convos = db.query(Conversation)\
        .filter(Conversation.user_id == user_id)\
        .order_by(Conversation.created_at)\
        .all()

    if not all_convos:
        raise HTTPException(status_code=404, detail="No conversations found for this user")

    history_text = "\n".join([
        f"{c.role}: {c.content}" for c in all_convos
    ])

    history_text = history_text[-12000:]

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
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

Be concise, factual, and compassionate. Write in second person.

Conversations:
{history_text}"""
        }]
    )

    summary = response.content[0].text
    memory = db.query(UserMemory)\
        .filter(UserMemory.user_id == user_id)\
        .first()

    if memory:
        memory.summary = summary
    else:
        db.add(UserMemory(user_id=user_id, summary=summary))

    db.commit()
    invalidate_memory_cache(user_id)

    return {
        "user_id": user_id,
        "memory": summary,
        "message": "Memory updated successfully"
    }


@router.get("/memory/{user_id}")
def get_memory(user_id: str, db: Session = Depends(get_db), _: None = Depends(verify_access_token)):

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
def get_history(user_id: str, skip: int = 0, limit: int = 50, db: Session = Depends(get_db), _: None = Depends(verify_access_token)):

    conversations = db.query(Conversation)\
        .filter(Conversation.user_id == user_id)\
        .order_by(Conversation.created_at)\
        .offset(skip)\
        .limit(limit)\
        .all()

    if not conversations:
        raise HTTPException(status_code=404, detail="No conversations found for this user")

    return {
        "user_id": user_id,
        "total_messages": len(conversations),
        "skip": skip,
        "limit": limit,
        "conversations": [
            {
                "session_id": c.session_id,
                "role": c.role,
                "content": c.content,
                "emotion": c.emotion,
                "created_at": str(c.created_at)
            }
            for c in conversations
        ]
    }


@router.get("/emotions/{user_id}")
def get_emotions(user_id: str, db: Session = Depends(get_db), _: None = Depends(verify_access_token)):

    logs = db.query(EmotionLog)\
        .filter(EmotionLog.user_id == user_id)\
        .order_by(EmotionLog.created_at)\
        .all()

    if not logs:
        raise HTTPException(status_code=404, detail="No emotion data found for this user")

    emotion_counts = {}
    for log in logs:
        emotion_counts[log.emotion] = emotion_counts.get(log.emotion, 0) + 1

    return {
        "user_id": user_id,
        "total_messages": len(logs),
        "emotion_breakdown": emotion_counts,
        "emotion_history": [
            {
                "emotion": log.emotion,
                "message_snippet": log.message_snippet,
                "created_at": str(log.created_at)
            }
            for log in logs
        ]
    }


@router.get("/patterns/{user_id}")
def get_patterns(user_id: str, db: Session = Depends(get_db), _: None = Depends(verify_access_token)):

    logs = db.query(EmotionLog)\
        .filter(EmotionLog.user_id == user_id)\
        .order_by(EmotionLog.created_at)\
        .all()

    if not logs:
        raise HTTPException(status_code=404, detail="No emotion data found for this user")

    if len(logs) < 3:
        raise HTTPException(status_code=400, detail="Not enough data yet — keep chatting and check back soon")

    history_text = "\n".join([
        f"{log.created_at} | {log.emotion} | {log.message_snippet}"
        for log in logs
    ])

    emotion_counts = {}
    for log in logs:
        emotion_counts[log.emotion] = emotion_counts.get(log.emotion, 0) + 1

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=600,
        messages=[{
            "role": "user",
            "content": f"""You are analyzing emotional patterns for a user of a workplace stress companion app.

Based on this emotion history, identify meaningful patterns and insights.

Focus on:
- Which emotions appear most frequently
- Any time-based patterns
- Recurring triggers mentioned in message snippets
- Whether things are improving or worsening over time
- One specific, actionable insight the user can act on

Be warm, specific, and honest. Write directly to the user in second person.
Keep it under 150 words. Do not be generic.

Emotion history:
{history_text}

Emotion counts: {emotion_counts}"""
        }]
    )

    return {
        "user_id": user_id,
        "total_messages_analyzed": len(logs),
        "emotion_breakdown": emotion_counts,
        "pattern_insight": response.content[0].text
    }


@router.get("/weekly-summary/{user_id}")
def get_weekly_summary(user_id: str, db: Session = Depends(get_db), _: None = Depends(verify_access_token)):

    from datetime import datetime, timedelta
    seven_days_ago = datetime.utcnow() - timedelta(days=7)

    logs = db.query(EmotionLog)\
        .filter(
            EmotionLog.user_id == user_id,
            EmotionLog.created_at >= seven_days_ago
        )\
        .order_by(EmotionLog.created_at)\
        .all()

    if not logs:
        raise HTTPException(status_code=404, detail="No data found for the past 7 days")

    emotion_counts = {}
    for log in logs:
        emotion_counts[log.emotion] = emotion_counts.get(log.emotion, 0) + 1

    dominant_emotion = max(emotion_counts, key=emotion_counts.get)

    history_text = "\n".join([
        f"{log.created_at.strftime('%A %H:%M')} | {log.emotion} | {log.message_snippet}"
        for log in logs
    ])

    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=500,
        messages=[{
            "role": "user",
            "content": f"""You are writing a weekly emotional wellness summary for a user.

Based on the past 7 days of data, write a short, warm, honest weekly check-in summary.

Include:
- How their week looked emotionally overall
- The most common trigger or theme
- One thing they did well
- One gentle suggestion for the week ahead

Keep it under 120 words. Be specific, not generic. Write directly to the user.

This week's data:
{history_text}

Emotion breakdown: {emotion_counts}
Dominant emotion: {dominant_emotion}"""
        }]
    )

    return {
        "user_id": user_id,
        "week_analyzed": "Past 7 days",
        "total_checkins": len(logs),
        "emotion_breakdown": emotion_counts,
        "dominant_emotion": dominant_emotion,
        "weekly_summary": response.content[0].text
    }


@router.get("/crisis-log/{user_id}")
def get_crisis_log(user_id: str, db: Session = Depends(get_db), _: None = Depends(verify_access_token)):

    logs = db.query(CrisisLog)\
        .filter(CrisisLog.user_id == user_id)\
        .order_by(CrisisLog.created_at)\
        .all()

    if not logs:
        return {"user_id": user_id, "crisis_events": 0, "log": []}

    return {
        "user_id": user_id,
        "crisis_events": len(logs),
        "log": [
            {
                "session_id": log.session_id,
                "message_snippet": log.message_snippet,
                "escalated": log.escalated,
                "created_at": str(log.created_at)
            }
            for log in logs
        ]
    }