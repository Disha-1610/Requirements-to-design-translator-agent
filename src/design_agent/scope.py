"""Scope-boundary helpers for Stage 8 check 11.

The original substring check on raw lowercased text had two problems:
  - Reworded scope creep slipped through ("crypto trading" vs "cryptocurrency trading").
  - Short out-of-scope phrases gave false positives inside longer, unrelated words.

Fix: reduce every text to a sorted tuple of stemmed tokens, then test for
word-boundary overlap rather than substring containment.

Stemming strategy
-----------------
We use a hand-rolled Porter-compatible suffix list rather than pulling in NLTK
or any other extra dependency.  It covers the word-endings that commonly vary
between a BRD's out-of-scope phrase and an FRD requirement's title/statement
(e.g. "trading" → "trade", "origination" → "originate", "transfers" → "transfer").
This is *not* a full morphological analyser — it only needs to be good enough
to catch the most common rewording patterns without false positives.

The function ``scope_hit`` is the single entry point.  It returns True when
*all* tokens of the out-of-scope phrase appear (in stemmed form) among the
stemmed tokens of the haystack text.  A phrase must have at least
``MIN_TOKENS`` tokens to be considered; shorter ones are skipped entirely to
avoid false positives from common words like "loan".
"""

from __future__ import annotations

import re

# Minimum number of meaningful tokens a scope phrase must have to trigger a match.
# Single-word phrases like "loan" match far too broadly.
MIN_TOKENS = 2

# Ordered list of suffixes to strip (longest first so only one pass is needed).
# Each entry is (suffix, min_stem_length) — the stem must keep at least
# min_stem_length characters so "transfer" → "transfer" (not "transf").
_SUFFIXES: list[tuple[str, int]] = [
    ("originations", 4),
    ("origination", 4),
    ("originating", 4),
    ("originated", 4),
    ("originate", 4),
    ("inations", 4),
    ("ination", 4),
    ("inating", 4),
    ("inated", 4),
    ("inate", 4),
    ("ations", 4),
    ("ation", 4),
    ("ating", 4),
    ("ated", 4),
    ("ate", 4),
    ("ings", 4),
    ("ing", 4),
    ("ions", 4),
    ("ion", 4),
    ("ers", 4),
    ("ies", 4),
    ("es", 4),
    ("ed", 4),
    ("er", 4),
    ("ly", 4),
    ("s", 4),
]

_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _stem(word: str) -> str:
    """Very lightweight stemmer: strip one suffix from the predefined list."""
    for suffix, min_len in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= min_len:
            return word[: -len(suffix)]
    return word


def _tokenize(text: str) -> frozenset[str]:
    """Lowercase, extract word/digit runs, stem each token."""
    return frozenset(_stem(t) for t in _TOKEN_RE.findall(text.lower()))


def scope_tokens(phrase: str) -> frozenset[str] | None:
    """Return stemmed token-set for *phrase*, or None if the phrase is too short to match."""
    tokens = _tokenize(phrase)
    if len(tokens) < MIN_TOKENS:
        return None
    return tokens


def scope_hit(phrase_tokens: frozenset[str], haystack: str) -> bool:
    """True when every token of *phrase_tokens* appears in the stemmed haystack."""
    hay_tokens = _tokenize(haystack)
    return phrase_tokens.issubset(hay_tokens)

