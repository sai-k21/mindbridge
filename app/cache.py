import redis
import os
import json
import logging
from dotenv import load_dotenv
from app.encryption import encrypt_text, decrypt_text

load_dotenv()

logger = logging.getLogger(__name__)

# Connect to Redis
try:
    redis_client = redis.from_url(
        os.getenv("REDIS_URL"),
        decode_responses=True,
        socket_connect_timeout=5
    )
    redis_client.ping()
    logger.info("Redis connected successfully")
    REDIS_AVAILABLE = True
except Exception as e:
    logger.warning(f"Redis unavailable: {e}. Running without cache.")
    redis_client = None
    REDIS_AVAILABLE = False


def get_cached_memory(user_id: str) -> str | None:
    if not REDIS_AVAILABLE:
        return None
    try:
        cached = redis_client.get(f"memory:{user_id}")
        if cached:
            logger.info(f"Cache HIT for memory:{user_id}")
            return decrypt_text(cached)
        logger.info(f"Cache MISS for memory:{user_id}")
        return None
    except Exception as e:
        logger.warning(f"Cache read error: {e}")
        return None


def set_cached_memory(user_id: str, summary: str, ttl: int = 3600):
    if not REDIS_AVAILABLE:
        return
    try:
        redis_client.setex(f"memory:{user_id}", ttl, encrypt_text(summary))
        logger.info(f"Cache SET for memory:{user_id} TTL={ttl}s")
    except Exception as e:
        logger.warning(f"Cache write error: {e}")


def invalidate_memory_cache(user_id: str):
    if not REDIS_AVAILABLE:
        return
    try:
        redis_client.delete(f"memory:{user_id}")
        logger.info(f"Cache INVALIDATED for memory:{user_id}")
    except Exception as e:
        logger.warning(f"Cache invalidation error: {e}")


def check_and_increment_daily_usage(limit: int = None) -> bool:
    """
    Increments today's global message counter and returns whether we're
    still under the daily budget. Fails OPEN (returns True) if Redis is
    unavailable, since a demo that degrades to "no budget cap" is safer
    than one that silently refuses to work when the cache is down.
    """
    if not REDIS_AVAILABLE:
        return True

    if limit is None:
        limit = int(os.getenv("DAILY_MESSAGE_LIMIT", "150"))

    from datetime import date, timezone, datetime
    key = f"daily_usage:{datetime.now(timezone.utc).date().isoformat()}"

    try:
        count = redis_client.incr(key)
        if count == 1:
            # First increment of the day — set expiry with a safety margin
            # past 24h so a slow clock skew can't leave it uncapped.
            redis_client.expire(key, 60 * 60 * 26)
        return count <= limit
    except Exception as e:
        logger.warning(f"Budget guard check failed: {e}")
        return True


def get_cache_stats() -> dict:
    if not REDIS_AVAILABLE:
        return {"status": "unavailable"}
    try:
        info = redis_client.info()
        return {
            "status": "connected",
            "used_memory": info.get("used_memory_human"),
            "total_commands": info.get("total_commands_processed"),
            "connected_clients": info.get("connected_clients"),
            "keyspace_hits": info.get("keyspace_hits"),
            "keyspace_misses": info.get("keyspace_misses")
        }
    except Exception as e:
        return {"status": f"error: {e}"}