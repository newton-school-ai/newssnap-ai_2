"""NewsSnap AI - Redis caching utilities for feed and pre-computed content."""

import json
import logging
from typing import Any, List, Optional

import redis

from src.config.settings import settings

logger = logging.getLogger(__name__)

# Global client cache
_redis_client: Optional[redis.Redis] = None
_custom_redis_client: Optional[Any] = None


def get_redis_client() -> Optional[redis.Redis]:
    """Retrieve or initialize the Redis client instance.

    Returns:
        A Redis client instance if available, or None if connection fails.
    """
    global _redis_client, _custom_redis_client

    if _custom_redis_client is not None:
        return _custom_redis_client

    if _redis_client is not None:
        return _redis_client

    try:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=1.5,
            socket_connect_timeout=1.5,
        )
        return _redis_client
    except Exception as e:
        logger.warning(f"Failed to connect to Redis at {settings.REDIS_URL}: {e}")
        return None


def set_custom_redis_client(client: Optional[Any]) -> None:
    """Set a custom or mock Redis client (useful for unit testing).

    Args:
        client: Mock or custom Redis instance.
    """
    global _custom_redis_client
    _custom_redis_client = client


def build_feed_cache_key(
    user_id: Optional[str],
    language: str,
    categories: Optional[List[str]] = None,
    time_range: Optional[str] = None,
) -> str:
    """Construct a standardized Redis key for feed caching.

    Args:
        user_id: The UUID string of the user, or None for guest.
        language: The language code (e.g. 'en', 'hi').
        categories: Optional list of category slugs.
        time_range: Optional time range string (e.g. '24h').

    Returns:
        A cache key string such as 'feed:usr-123:en:business,sports:24h'.
    """
    user_part = user_id if user_id else "guest"
    cat_part = ",".join(sorted(categories)) if categories else "all"
    tr_part = time_range.strip().lower() if time_range else "all"
    return f"feed:{user_part}:{language}:{cat_part}:{tr_part}"


def get_cached_feed(cache_key: str) -> Optional[List[dict]]:
    """Retrieve pre-computed feed items from Redis.

    Args:
        cache_key: The cache key string.

    Returns:
        A list of feed item dictionaries if found, otherwise None.
    """
    client = get_redis_client()
    if client is None:
        return None

    try:
        data = client.get(cache_key)
        if data:
            return json.loads(data)
    except Exception as e:
        logger.debug(f"Redis get failed for key {cache_key}: {e}")

    return None


def set_cached_feed(cache_key: str, items: List[dict], ttl: int = 300) -> bool:
    """Store pre-computed feed items into Redis with an expiration time.

    Args:
        cache_key: The cache key string.
        items: List of feed item dictionaries (typically up to 50 items).
        ttl: Time-to-live in seconds (default: 300s / 5 minutes).

    Returns:
        True if caching succeeded, False otherwise.
    """
    client = get_redis_client()
    if client is None:
        return False

    try:
        serialized = json.dumps(items)
        client.setex(cache_key, ttl, serialized)
        return True
    except Exception as e:
        logger.debug(f"Redis set failed for key {cache_key}: {e}")
        return False


def invalidate_feed_cache(user_id: Optional[str] = None) -> int:
    """Invalidate cached feeds.

    If user_id is provided, invalidates feeds for that specific user.
    If user_id is None, invalidates all pre-computed feeds across all users.

    Args:
        user_id: Optional user UUID string.

    Returns:
        Number of keys deleted.
    """
    client = get_redis_client()
    if client is None:
        return 0

    deleted_count = 0
    pattern = f"feed:{user_id}:*" if user_id else "feed:*"

    try:
        keys = list(client.scan_iter(match=pattern, count=100))
        if keys:
            deleted_count = client.delete(*keys)
    except Exception as e:
        logger.debug(f"Redis cache invalidation failed for pattern {pattern}: {e}")

    return deleted_count
