"""Helpers for turning text into simple slugs."""

import re


def slugify(text: str) -> str:
    """Lowercase *text* and replace each run of whitespace with a hyphen."""
    return re.sub(r"\s+", "-", text.lower())
