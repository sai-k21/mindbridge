```markdown
# MindBridge

A memory-driven AI companion for workplace stress — built with FastAPI, PostgreSQL, and Claude API.

## The Problem It Solves

Existing AI companions like Replika, Wysa, and Woebot reset after every session. 
MindBridge remembers you across every conversation — your stressors, what helped, 
your patterns — solving the core gap every competitor misses.

## Architecture

```
User → FastAPI REST API → Claude API (claude-opus-4-5)
                       → PostgreSQL (conversation history + user memory)
```

## Tech Stack

- **Backend:** Python, FastAPI
- **Database:** PostgreSQL (Render)
- **AI:** Anthropic Claude API
- **ORM:** SQLAlchemy
- **Deployment:** Render

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/chat` | Send a message, get a response |
| POST | `/memory/update` | Summarize and store user memory across sessions |
| GET | `/` | Health check |

## Key Design Decisions

**Why persistent memory?**
Every existing competitor resets after each session. MindBridge stores 
conversation history per user and injects a summarized memory into every 
new session — so the agent remembers your stressors, patterns, and what 
helped before.

**Why FastAPI?**
Async-ready, automatic API docs via Swagger UI, Pydantic validation 
out of the box — production-grade from day one.

**Why SQLAlchemy?**
Clean ORM abstraction over PostgreSQL — schema changes are code changes, 
not raw SQL migrations.

## Local Setup

```bash
git clone https://github.com/sai-k21/mindbridge.git
cd mindbridge
uv venv
.venv\Scripts\activate
uv pip install -r requirements.txt
```

Create `.env` file:
```
DATABASE_URL=your_postgresql_url
ANTHROPIC_API_KEY=your_anthropic_key
```

Run:
```bash
uvicorn app.main:app --reload
```

Open: `http://127.0.0.1:8000/docs`

## Roadmap

- [x] Phase 1: FastAPI + PostgreSQL + Claude API
- [x] Phase 2: Persistent memory across sessions
- [x] Phase 3: Emotion detection and tone adaptation
- [x] Phase 4: Pattern recognition and weekly insights
- [ ] Phase 5: Crisis detection and guardrails
- [ ] Phase 6: Multi-agent orchestration with LangGraph
- [ ] Phase 7: Redis caching + observability
- [ ] Phase 8: Full deployment + React frontend
```

Save — **Ctrl+S**

Then run the push commands:

```powershell
git init
git add .
git commit -m "Phase 1: FastAPI + PostgreSQL + Claude API working"
git branch -M main
git remote add origin https://github.com/sai-k21/mindbridge.git
git push -u origin main
```