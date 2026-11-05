"""Multi-key manager: loads OPENROUTER_KEY_1..N and GEMINI_KEY_1..N,
rotates round-robin, and returns keys in rotated order for failover."""

import os
import threading

from dotenv import load_dotenv

load_dotenv()


class KeyManager:
    MAX_KEYS = 50

    def __init__(self):
        self._lock = threading.Lock()
        self._openrouter = (
            self._load_numbered("OPENROUTER_KEY")
            or self._load_legacy("OPENROUTER_API_KEY", "AI_API_KEY")
        )
        self._gemini = (
            self._load_numbered("GEMINI_KEY")
            or self._load_legacy("GEMINI_API_KEY", "GOOGLE_API_KEY")
        )
        self._or_counter = 0
        self._gem_counter = 0

    @classmethod
    def _load_numbered(cls, prefix):
        keys = []
        for i in range(1, cls.MAX_KEYS + 1):
            raw = os.getenv(f"{prefix}_{i}")
            if raw is None:
                break
            value = raw.strip()
            if value:
                keys.append(value)
        return keys

    @staticmethod
    def _load_legacy(*names):
        for name in names:
            value = (os.getenv(name) or "").strip()
            if value:
                return [value]
        return []

    def _rotate(self, keys, counter_attr):
        with self._lock:
            n = len(keys)
            if n == 0:
                return []
            start = getattr(self, counter_attr) % n
            setattr(self, counter_attr, (start + 1) % n)
            return keys[start:] + keys[:start]

    def openrouter_keys_rotated(self):
        return self._rotate(self._openrouter, "_or_counter")

    def gemini_keys_rotated(self):
        return self._rotate(self._gemini, "_gem_counter")

    def has_openrouter(self):
        return bool(self._openrouter)

    def has_gemini(self):
        return bool(self._gemini)


key_manager = KeyManager()
