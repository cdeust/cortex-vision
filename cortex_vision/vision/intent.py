"""Classify an extracted text snippet as a Cortex recall query or a memory.

Heuristic, deterministic, and locally reasoned — no model call. The aim is a
sensible default for ``mode='auto'``; the caller can always override by passing
mode='recall' or mode='remember' to the look tool.
"""

from __future__ import annotations

import re

# Leading/early phrases that signal an explicit "store this" instruction.
_REMEMBER_MARKERS = (
    "remember", "note that", "make a note", "save this", "save that",
    "store this", "store that", "don't forget", "do not forget",
    "for the record", "keep in mind", "take note",
)

# Phrases anywhere that signal a question / lookup.
_RECALL_MARKERS = (
    "what did", "what do we", "what's the", "what is the", "do we know",
    "have we", "did we", "remind me", "recall", "look up", "search for",
    "find the", "what was", "is there", "are there",
)

# First-token interrogatives.
_QUESTION_WORDS = (
    "what", "who", "when", "where", "why", "how", "which", "whose",
    "is", "are", "do", "does", "did", "can", "could", "should", "would",
    "was", "were", "will", "has", "have",
)

_STOPWORDS = frozenset(
    {
        "the", "a", "an", "to", "of", "in", "on", "at", "for", "and", "or",
        "but", "is", "are", "was", "were", "be", "been", "this", "that",
        "these", "those", "i", "you", "we", "it", "do", "did", "does", "what",
        "who", "when", "where", "why", "how", "which", "with", "about", "from",
        "as", "by", "my", "our", "your", "me", "us", "so", "if", "then",
        "remember", "note", "save", "store", "recall", "please",
    }
)


def classify(text_in: str) -> str:
    """Return 'recall' or 'remember' for a text snippet."""
    text = text_in.strip().lower()
    if not text:
        return "remember"
    head = text[:40]
    for marker in _REMEMBER_MARKERS:
        if text.startswith(marker) or f" {marker}" in head:
            return "remember"
    if text.endswith("?"):
        return "recall"
    for marker in _RECALL_MARKERS:
        if marker in text:
            return "recall"
    if text.split()[0] in _QUESTION_WORDS:
        return "recall"
    # A plain declarative statement is something to capture.
    return "remember"


def suggest_tags(text_in: str, limit: int = 5) -> list[str]:
    """Pick up to ``limit`` salient content words as candidate tags."""
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9_-]{2,}", text_in.lower())
    tags: list[str] = []
    for word in words:
        if word in _STOPWORDS or word in tags:
            continue
        tags.append(word)
        if len(tags) >= limit:
            break
    return tags
