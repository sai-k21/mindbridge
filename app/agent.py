from typing import TypedDict, Optional
from langgraph.graph import StateGraph, END
from sqlalchemy.orm import Session
from app.models import Conversation, UserMemory, EmotionLog, CrisisLog
import anthropic
import os
import logging
logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

# Crisis keywords
CRISIS_KEYWORDS = [
    "kill myself", "want to die", "end my life", "suicide", "suicidal",
    "don't want to exist", "better off dead", "no reason to live",
    "can't go on", "give up on life", "hurt myself", "self harm"
]

TONE_INSTRUCTIONS = {
    "calm": "The user seems calm. Be warm, conversational, and exploratory. Ask thoughtful open-ended questions.",
    "stressed": "The user is stressed. Be grounded and validating. Acknowledge what they are carrying before asking anything.",
    "anxious": "The user is anxious. Slow down. Be very gentle. Use shorter sentences. Give them space to breathe before exploring.",
    "overwhelmed": "The user is overwhelmed. Be extremely gentle. Focus on one thing at a time. Do not ask multiple questions.",
    "crisis": "The user may be in crisis. Do not ask questions. Immediately express care and refer them to professional help. Always mention the 988 Suicide and Crisis Lifeline."
}

SYSTEM_PROMPT = """You are MindBridge, a compassionate AI companion 
for people dealing with workplace stress. You listen deeply, ask 
thoughtful questions, and gently challenge unhelpful thinking patterns. 
You never give hollow affirmations. If someone seems to be in crisis, 
always refer them to professional help or the 988 crisis line (US)."""


# ── State — shared across all agents ─────────────────────────────────────────

class AgentState(TypedDict):
    user_id: str
    session_id: str
    message: str
    emotion: Optional[str]
    memory_summary: Optional[str]
    conversation_history: Optional[list]
    reply: Optional[str]
    crisis_escalated: bool
    db: object


# ── Agent 1: Emotion Agent ────────────────────────────────────────────────────

def emotion_agent(state: AgentState) -> AgentState:
    message = state["message"]

    # Fast rule-based crisis check
    message_lower = message.lower()
    if any(keyword in message_lower for keyword in CRISIS_KEYWORDS):
        state["emotion"] = "crisis"
        return state

    # LLM-based classification — Haiku is plenty for a 5-way classification
    # task and this call runs on every single message, so the model choice
    # here matters a lot for both latency and cost.
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
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

    state["emotion"] = emotion
    return state


# ── Agent 2: Memory Agent ─────────────────────────────────────────────────────

def memory_agent(state: AgentState) -> AgentState:
    from app.cache import get_cached_memory, set_cached_memory
    import time

    db = state["db"]
    user_id = state["user_id"]
    session_id = state["session_id"]

    # Get conversation history for this session
    history = db.query(Conversation)\
        .filter(Conversation.session_id == session_id)\
        .order_by(Conversation.created_at)\
        .all()

    state["conversation_history"] = [
        {"role": h.role, "content": h.content} for h in history
    ]

    # Try cache first
    start = time.time()
    cached = get_cached_memory(user_id)

    if cached:
        state["memory_summary"] = cached
        logger.info(f"Memory retrieved from cache in {(time.time()-start)*1000:.1f}ms")
    else:
        # Cache miss — hit PostgreSQL
        memory = db.query(UserMemory)\
            .filter(UserMemory.user_id == user_id)\
            .first()

        if memory and memory.summary:
            state["memory_summary"] = memory.summary
            # Store in cache for next time
            set_cached_memory(user_id, memory.summary)
            logger.info(f"Memory retrieved from DB in {(time.time()-start)*1000:.1f}ms — cached for next request")
        else:
            state["memory_summary"] = None

    return state

# ── Agent 3: Conversation Agent ───────────────────────────────────────────────

def conversation_agent(state: AgentState) -> AgentState:
    emotion = state["emotion"]
    memory_summary = state["memory_summary"]
    history = state["conversation_history"] or []

    # Build dynamic system prompt
    system = SYSTEM_PROMPT
    system += f"\n\nCurrent emotional state detected: {emotion.upper()}"
    system += f"\n{TONE_INSTRUCTIONS[emotion]}"

    if memory_summary:
        system += f"\n\nWhat you remember about this user from past sessions:\n{memory_summary}"
        system += "\n\nUse this memory naturally — don't announce that you remember things."

    response = client.messages.create(
        model="claude-opus-4-5",
        max_tokens=1000,
        system=system,
        messages=history
    )

    state["reply"] = response.content[0].text
    state["crisis_escalated"] = False
    return state


# ── Crisis Agent ──────────────────────────────────────────────────────────────

def crisis_agent(state: AgentState) -> AgentState:
    state["reply"] = """I hear you, and I'm really glad you reached out right now.

What you're feeling matters, and you don't have to face this alone.

Please reach out to someone who can help right now:
- Call or text 988 (Suicide and Crisis Lifeline, US) — available 24/7
- Text HOME to 741741 (Crisis Text Line)
- Call 911 or go to your nearest emergency room if you are in immediate danger

You deserve real support from someone trained to help. I care about what happens to you."""

    state["crisis_escalated"] = True
    return state


# ── Router — decides which path to take ──────────────────────────────────────

def route_after_emotion(state: AgentState) -> str:
    if state["emotion"] == "crisis":
        return "crisis_agent"
    return "memory_agent"


# ── Build the graph ───────────────────────────────────────────────────────────

def build_graph():
    graph = StateGraph(AgentState)

    # Add nodes
    graph.add_node("emotion_agent", emotion_agent)
    graph.add_node("memory_agent", memory_agent)
    graph.add_node("conversation_agent", conversation_agent)
    graph.add_node("crisis_agent", crisis_agent)

    # Set entry point
    graph.set_entry_point("emotion_agent")

    # Add conditional routing after emotion detection
    graph.add_conditional_edges(
        "emotion_agent",
        route_after_emotion,
        {
            "memory_agent": "memory_agent",
            "crisis_agent": "crisis_agent"
        }
    )

    # Normal flow
    graph.add_edge("memory_agent", "conversation_agent")
    graph.add_edge("conversation_agent", END)
    graph.add_edge("crisis_agent", END)

    return graph.compile()


# Compiled graph — import this in routes
mindbridge_graph = build_graph()