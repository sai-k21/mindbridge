import logging
import time
from fastapi import FastAPI, Request
from app.database import Base, engine
from app.routes import chat

# Structured logging setup
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)
logger = logging.getLogger(__name__)

Base.metadata.create_all(bind=engine)

app = FastAPI(title="MindBridge API")
app.include_router(chat.router)


# Request timing middleware
@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    duration = (time.time() - start) * 1000
    logger.info(f"{request.method} {request.url.path} | {response.status_code} | {duration:.1f}ms")
    return response


@app.get("/")
def root():
    return {"status": "MindBridge is running"}


@app.get("/health")
def health():
    from app.cache import get_cache_stats, REDIS_AVAILABLE
    from app.database import engine
    from sqlalchemy import text

    # Check DB
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"error: {e}"

    return {
        "status": "ok",
        "database": db_status,
        "redis": get_cache_stats(),
        "redis_available": REDIS_AVAILABLE
    }