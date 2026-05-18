from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from app.database import get_db
from app.models import Conversation, UserMemory, EmotionLog, CrisisLog
from app.agent import mindbridge_graph
from app.schemas import ChatRequest
from slowapi import Limiter
from slowapi.util import get_remote_address

import anthropic
import os


limiter = Limiter(key_func=get_remote_address)

router = APIRouter()
client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Crisis keywords for fast rule-based detection
CRISIS_KEYWORDS = [
    "kill myself", "want to die", "end my life", "suicide", "suicidal",
    "don't want to exist", "better off dead", "no reason to live",
    "can't go on", "give up on life", "hurt myself", "self harm"
]

# Tone instructions per emotion
TONE_INSTRUCTIONS = {
    "calm": "The user seems calm. Be warm, conversational, and exploratory. Ask thoughtful open-ended questions.",
    "stressed": "The user is stressed. Be grounded and validating. Acknowledge what they are carrying before asking anything.",
    "anxious": "The user is anxious. Slow down. Be very gentle. Use shorter sentences. Give them space to breathe before exploring.",
    "overwhelmed": "The user is overwhelmed. Be extremely gentle. Focus on one thing at a time. Do not ask multiple questions.",
    "crisis": "The user may be in crisis. Do not ask questions. Immediately express care and refer them to professional help. Always mention the 988 Suicide and Crisis Lifeline (call or text 988 in the US) and encourage them to reach out to someone they trust."
}

SYSTEM_PROMPT = """You are MindBridge, a compassionate AI companion 
for people dealing with workplace stress. You listen deeply, ask 
thoughtful questions, and gently challenge unhelpful thinking patterns. 
You never give hollow affirmations like 'you are amazing'. 
If someone seems to be in crisis, always refer them to 
professional help or the 988 crisis line (US)."""


def check_crisis_keywords(message: str) -> bool:
    message_lower = message.lower()
    return any(keyword in message_lower for keyword in CRISIS_KEYWORDS)


def detect_emotion(message: str) -> str:

    # Fast rule-based crisis check first
    if check_crisis_keywords(message):
        return "crisis"

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=50,
        messages=[{
            "role": "user",
            "content": f"""Classify the emotional state in this message into exactly one word.
Choose only from: calm, stressed, anxious, overwhelmed, crisis

Rules:
- crisis: any mention of self-harm, suicide, hopelessness, not wanting to exist
- overwhelmed: completely unable to cope, everything is too much
- anxious: worry, fear, nervousness, panic
- stressed: pressure, tension, difficulty but still coping
- calm: neutral or positive

Message: "{message}"

Respond with only one word, nothing else."""
        }]
    )
    emotion = response.content[0].text.strip().lower()
    if emotion not in ["calm", "stressed", "anxious", "overwhelmed", "crisis"]:
        emotion = "stressed"
    return emotion


def build_crisis_response() -> str:
    return """I hear you, and I'm really glad you reached out right now.

What you're feeling matters, and you don't have to face this alone.

Please reach out to someone who can help right now:
- Call or text 988 (Suicide and Crisis Lifeline, US) — available 24/7
- Text HOME to 741741 (Crisis Text Line)
- Call 911 or go to your nearest emergency room if you are in immediate danger

You deserve real support from someone trained to help. I care about what happens to you."""


@router.post("/chat")
@limiter.limit("10/minute")
def chat(request: Request, chat_request: ChatRequest, db: Session = Depends(get_db)):
    user_id = chat_request.user_id
    session_id = chat_request.session_id
    message = chat_request.message
    # Save user message first
    db.add(Conversation(
        user_id=user_id,
        session_id=session_id,
        role="user",
        content=message
    ))
    db.commit()

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
        "memory_active": result["memory_summary"] is not None
    }

@router.post("/memory/update")
def update_memory(user_id: str, db: Session = Depends(get_db)):

    all_convos = db.query(Conversation)\
        .filter(Conversation.user_id == user_id)\
        .order_by(Conversation.created_at)\
        .all()

    if not all_convos:
        raise HTTPException(status_code=404, detail="No conversations found for this user")

    history_text = "\n".join([
        f"{c.role}: {c.content}" for c in all_convos
    ])

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
                "emotion": c.emotion,
                "created_at": str(c.created_at)
            }
            for c in conversations
        ]
    }


@router.get("/emotions/{user_id}")
def get_emotions(user_id: str, db: Session = Depends(get_db)):

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
def get_patterns(user_id: str, db: Session = Depends(get_db)):

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
        model="claude-opus-4-5",
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
def get_weekly_summary(user_id: str, db: Session = Depends(get_db)):

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
        model="claude-opus-4-5",
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
def get_crisis_log(user_id: str, db: Session = Depends(get_db)):

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