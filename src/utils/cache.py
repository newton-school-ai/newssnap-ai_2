"""NewsSnap AI - Redis and in-memory fallback cache utility.

Provides robust caching with Redis support and automatic seamless
in-memory fallback for local development and test environments.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple, Union

import redis

from src.config.settings import settings

logger = logging.getLogger(__name__)


class JSONEncoder(json.JSONEncoder):
    """Custom JSON encoder supporting datetime and UUID objects."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, uuid.UUID):
            return str(obj)
        return super().default(obj)


# In-memory stores for fallback and tests
_in_memory_kv: Dict[str, Tuple[Any, float]] = {}
_in_memory_zsets: Dict[str, Dict[str, float]] = {}
_redis_client_override: Optional[Any] = None
_redis_client_instance: Optional[redis.Redis] = None
_redis_checked: bool = False


def set_redis_client(client: Optional[Any]) -> None:
    """Explicitly set or override the Redis client (useful for unit tests)."""
    global _redis_client_override, _redis_client_instance
    _redis_client_override = client
    _redis_client_instance = client


def get_redis_client() -> Optional[redis.Redis]:
    """
    Get an active Redis client instance if available.
    Returns None if Redis is unreachable or not configured.
    """
    global _redis_client_instance, _redis_checked

    if _redis_client_override is not None:
        return _redis_client_override

    if _redis_client_instance is not None:
        return _redis_client_instance

    try:
        client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_connect_timeout=0.5,
            socket_timeout=0.5,
        )
        # Test connection
        client.ping()
        _redis_client_instance = client
        return _redis_client_instance
    except Exception as exc:
        if not _redis_checked:
            logger.info("Redis not available (%s); using in-memory cache fallback.", exc)
            _redis_checked = True
        return None


def get_cache(key: str) -> Optional[Any]:
    """
    Retrieve and deserialize a value from cache by key.
    Checks Redis first; falls back to in-memory store.
    """
    client = get_redis_client()
    if client is not None:
        try:
            val = client.get(key)
            if val is not None:
                return json.loads(val)
        except Exception as exc:
            logger.debug("Redis get error for %s: %s; checking in-memory fallback", key, exc)

    # In-memory fallback
    item = _in_memory_kv.get(key)
    if item is not None:
        val, expiry = item
        if time.time() <= expiry:
            return json.loads(json.dumps(val, cls=JSONEncoder))
        else:
            _in_memory_kv.pop(key, None)

    return None


def set_cache(key: str, value: Any, ttl_seconds: int = 300) -> bool:
    """
    Serialize and store a value in cache with a TTL (seconds).
    Saves to Redis if available, and also updates in-memory cache.
    """
    payload = json.dumps(value, cls=JSONEncoder)
    expiry = time.time() + ttl_seconds

    # Always update in-memory
    _in_memory_kv[key] = (json.loads(payload), expiry)

    client = get_redis_client()
    if client is not None:
        try:
            client.setex(key, ttl_seconds, payload)
            return True
        except Exception as exc:
            logger.debug("Redis set error for %s: %s", key, exc)

    return True


def delete_cache(key: str) -> bool:
    """Delete a key from Redis and in-memory cache."""
    _in_memory_kv.pop(key, None)
    client = get_redis_client()
    if client is not None:
        try:
            client.delete(key)
            return True
        except Exception as exc:
            logger.debug("Redis delete error for %s: %s", key, exc)
    return True


def clear_cache(pattern: str = "*") -> bool:
    """Clear keys matching pattern from Redis and in-memory cache."""
    global _in_memory_kv, _in_memory_zsets
    _in_memory_kv.clear()
    _in_memory_zsets.clear()

    client = get_redis_client()
    if client is not None:
        try:
            keys = client.keys(pattern)
            if keys:
                client.delete(*keys)
            return True
        except Exception as exc:
            logger.debug("Redis clear error: %s", exc)
    return True


def zadd(key: str, mapping: Dict[str, float]) -> bool:
    """Add member-score pairs to a sorted set in Redis or in-memory fallback."""
    if key not in _in_memory_zsets:
        _in_memory_zsets[key] = {}
    _in_memory_zsets[key].update(mapping)

    client = get_redis_client()
    if client is not None:
        try:
            client.zadd(key, mapping)
            return True
        except Exception as exc:
            logger.debug("Redis zadd error: %s", exc)
    return True


def zrevrange(
    key: str,
    start: int = 0,
    stop: int = -1,
    withscores: bool = False,
) -> List[Union[str, Tuple[str, float]]]:
    """Retrieve members in a sorted set in descending score order."""
    client = get_redis_client()
    if client is not None:
        try:
            return client.zrevrange(key, start, stop, withscores=withscores)
        except Exception as exc:
            logger.debug("Redis zrevrange error: %s", exc)

    # In-memory fallback
    zset = _in_memory_zsets.get(key, {})
    sorted_items = sorted(zset.items(), key=lambda x: x[1], reverse=True)
    end = None if stop == -1 else stop + 1
    sliced = sorted_items[start:end]
    if withscores:
        return sliced
    return [item[0] for item in sliced]


def zscore(key: str, member: str) -> Optional[float]:
    """Get the score of a member in a sorted set."""
    client = get_redis_client()
    if client is not None:
        try:
            return client.zscore(key, member)
        except Exception as exc:
            logger.debug("Redis zscore error: %s", exc)

    return _in_memory_zsets.get(key, {}).get(member)
