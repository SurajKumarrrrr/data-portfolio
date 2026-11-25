"""German text normalisation, tokenisation and negation marking."""

from __future__ import annotations

import re
import unicodedata

_UMLAUTS = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*|[.,!?;:]")

NEGATION_CUES = frozenset(
    {"nicht", "kein", "keine", "keinen", "keinem", "keiner", "keines", "nie", "niemals",
     "nichts", "ohne", "weder", "nirgends"}
)
# a negation scope ends at punctuation or at a contrastive conjunction
SCOPE_BREAKERS = frozenset({".", ",", "!", "?", ";", ":", "aber", "doch", "jedoch", "sondern"})
CONTRAST_CUES = frozenset({"aber", "doch", "jedoch", "allerdings", "sondern", "trotzdem"})


def normalize(text: str) -> str:
    """Lower-case, NFC-normalise and fold umlauts (``ä`` -> ``ae``, ``ß`` -> ``ss``).

    Folding makes "Verhältnis" and the transliterated "Verhaeltnis" the same token.
    """
    text = unicodedata.normalize("NFC", text).lower()
    return text.translate(_UMLAUTS)


def tokenize(text: str) -> list[str]:
    """Split normalised text into word and punctuation tokens."""
    return _TOKEN_RE.findall(normalize(text))


def mark_negation(tokens: list[str]) -> list[str]:
    """Prefix tokens inside a negation scope with ``NEG_``.

    ``["ist", "nicht", "gut", "."]`` -> ``["ist", "nicht", "NEG_gut", "."]``.
    This lets a linear bag-of-words model learn that ``NEG_gut`` is negative while ``gut``
    is positive - a classic trick from sentiment analysis (Das & Chen 2001, Pang et al. 2002).
    """
    out: list[str] = []
    in_scope = False
    for tok in tokens:
        if tok in SCOPE_BREAKERS:
            in_scope = False
            out.append(tok)
        elif tok in NEGATION_CUES:
            in_scope = True
            out.append(tok)
        else:
            out.append(f"NEG_{tok}" if in_scope else tok)
    return out


def tokenize_with_negation(text: str) -> list[str]:
    """Tokeniser used by the negation-aware TF-IDF baseline (module-level -> picklable)."""
    return mark_negation(tokenize(text))


def has_negation(text: str) -> bool:
    return any(t in NEGATION_CUES for t in tokenize(text))


def has_contrast(text: str) -> bool:
    return any(t in CONTRAST_CUES for t in tokenize(text))


def is_transliterated(text: str) -> bool:
    """Heuristic: text uses ae/oe/ue spellings instead of umlauts."""
    return bool(re.search(r"(ae|oe|ue)", text.lower())) and not re.search(r"[äöüß]", text.lower())
