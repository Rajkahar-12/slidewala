"""Redis-backed cache for generated presentations.
Silently disables itself if Redis is unavailable."""

import hashlib
import json
import logging
import os
import threading

logger = logging.getLogger(__name__)

try:
    import redis
except ImportError:
    redis = None

CACHE_VERSION = "v1"  # bump when prompt/schema changes

_client = None
_client_lock = threading.Lock()
_cache_disabled = False


def _get_client():
    global _client, _cache_disabled
    if _client is not None:
        return _client
    if _cache_disabled:
        return None

    with _client_lock:
        if _client is not None:
            return _client
        if _cache_disabled:
            return None

        if redis is None:
            logger.warning("redis package missing; cache disabled.")
            _cache_disabled = True
            return None

        url = (os.getenv("REDIS_URL") or os.getenv("CELERY_BROKER_URL") or "").strip()
        if not url:
            logger.warning("REDIS_URL not set; cache disabled.")
            _cache_disabled = True
            return None

        try:
            client = redis.Redis.from_url(
                url, decode_responses=True,
                socket_timeout=2, socket_connect_timeout=2,
            )
            client.ping()
            _client = client
            logger.info("Cache Redis connected.")
            return client
        except Exception as exc:
            logger.warning("Redis unreachable (%s); cache disabled.", exc)
            _cache_disabled = True
            return None


def make_cache_key(inputs):
    canonical = json.dumps(
        {
            "v": CACHE_VERSION,
            "topic": inputs["topic"].strip().lower(),
            "slides": inputs["slides"],
            "audience": inputs["audience"],
            "tone": inputs["tone"],
            "theme": inputs["theme"],
            "content_length": inputs["content_length"],
            "deck_type": inputs["deck_type"],
        },
        sort_keys=True, ensure_ascii=False,
    )
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    return f"slidewala:deck:{digest}"


def get_cached_deck(key):
    client = _get_client()
    if not client:
        return None
    try:
        raw = client.get(key)
        return json.loads(raw) if raw else None
    except Exception as exc:
        logger.warning("Cache get failed: %s", exc)
        return None


def set_cached_deck(key, deck):
    client = _get_client()
    if not client:
        return
    try:
        ttl = int(os.getenv("AI_CACHE_TTL") or "86400")
        client.setex(key, ttl, json.dumps(deck, ensure_ascii=False))
    except Exception as exc:
        logger.warning("Cache set failed: %s", exc)
