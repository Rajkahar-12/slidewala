"""In-memory cache for generated presentations. 
No Redis required. Works perfectly on free tiers."""

import hashlib
import json
import logging
import os
import threading
import time

logger = logging.getLogger(__name__)

CACHE_VERSION = "v1"

class MemoryCache:
    def __init__(self):
        self._data = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            item = self._data.get(key)
            if item:
                if time.time() < item['expires']:
                    return item['value']
                else:
                    del self._data[key]
            return None

    def set(self, key, value, ttl):
        with self._lock:
            self._data[key] = {
                'value': value,
                'expires': time.time() + ttl
            }

# Global in-memory cache
_cache = MemoryCache()

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
    try:
        return _cache.get(key)
    except Exception as exc:
        logger.warning("Cache get failed: %s", exc)
        return None

def set_cached_deck(key, deck):
    try:
        ttl = int(os.getenv("AI_CACHE_TTL") or "86400")
        _cache.set(key, deck, ttl)
    except Exception as exc:
        logger.warning("Cache set failed: %s", exc)
