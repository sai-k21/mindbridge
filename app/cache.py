import redis
import os
import json
import logging
from dotenv import load_dotenv

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
            return cached
        logger.info(f"Cache MISS for memory:{user_id}")
        return None
    except Exception as e:
        logger.warning(f"Cache read error: {e}")
        return None


def set_cached_memory(user_id: str, summary: str, ttl: int = 3600):
    if not REDIS_AVAILABLE:
        return
    try:
        redis_client.setex(f"memory:{user_id}", ttl, summary)
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