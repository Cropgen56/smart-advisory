"""
core/i18n.py
============
A lightweight, zero-dependency translation utility for the advisory engine.

Usage:
    from core.i18n import I18n
    t = I18n("hi")
    t.get("spray.no_spray_title")                           # → "आज कोई स्प्रे नहीं"
    t.get("spray.fungal_message", chemical="Mancozeb", ...) # → "Mancozeb ... लगाएं"
"""

import json
import os
from typing import Any

# Directory containing all locale JSON files
_LOCALES_DIR = os.path.join(os.path.dirname(__file__), "..", "locales")

# In-memory cache: { "hi": { ... }, "en": { ... } }
_cache: dict = {}


def _load(lang: str) -> dict:
    """Load and cache a locale dictionary. Falls back to 'en' if not found."""
    if lang not in _cache:
        path = os.path.join(_LOCALES_DIR, f"{lang}.json")
        if not os.path.exists(path):
            # Fall back to English
            path = os.path.join(_LOCALES_DIR, "en.json")
        with open(path, encoding="utf-8") as f:
            _cache[lang] = json.load(f)
    return _cache[lang]


class I18n:
    """
    Translation accessor for a single language.

    Args:
        lang: BCP-47 language code (e.g. "en", "hi", "te", "ta", "kn").
              Falls back to English if the locale file is not found.
    """

    def __init__(self, lang: str = "en"):
        self.lang = lang
        self._strings = _load(lang)
        # Always keep English as fallback for missing keys
        self._fallback = _load("en") if lang != "en" else {}

    def get(self, key: str, **kwargs: Any) -> str:
        """
        Retrieve a translated string by dot-separated key, then
        format it with any provided keyword arguments.

        Example:
            t.get("spray.fungal_message", chemical="Mancozeb", dose="2 ml/L",
                  humidity=85, crit_humidity=80, temp=26, ndvi=0.55, ndvi_threshold=0.65)
        """
        # Try primary language first, then English fallback
        value = self._strings.get(key) or self._fallback.get(key, key)
        if kwargs:
            try:
                value = value.format(**kwargs)
            except (KeyError, ValueError):
                pass  # Return partially formatted string rather than crashing
        return value
