from typing import List, Optional
from app.services.llm import EMERGENCY_RESPONSE_TEXT
from app.services.rag import I_DONT_KNOW_RESPONSE


def score_red_flag(detected: bool, expected: str) -> bool:
    """Exact check: classifier decision matches golden label ('yes' or 'no')."""
    exp_bool = (expected or "").strip().lower() == "yes"
    return bool(detected) == exp_bool


def score_emergency_text(reply: str) -> bool:
    """Exact check: chat reply contains the required emergency text word for word."""
    if not reply:
        return False
    return EMERGENCY_RESPONSE_TEXT in reply.strip()


def score_sources_present(sources: List[str]) -> bool:
    """Exact check: at least one document source is cited."""
    return bool(sources and len(sources) > 0)


def score_sources_match(sources: List[str], expected_source: str) -> bool:
    """
    Checks if any of the cited sources matches the expected source pattern.
    Supports pipe-separated alternatives like 'file > section1 | file > section2'.
    Normalizes delimiter symbols like '›' vs '>'.
    """
    if not expected_source or expected_source.strip().lower() == "none":
        return True
    if not sources:
        return False

    def _norm(s: str) -> str:
        return s.replace("›", ">").replace("  ", " ").strip().lower()

    alternatives = [_norm(alt) for alt in expected_source.split("|")]
    for s in sources:
        s_norm = _norm(s)
        for alt in alternatives:
            if alt in s_norm or s_norm in alt:
                return True
    return False


def score_idk(reply: str) -> bool:
    """Exact check: unanswerable policy question gets the fixed I-don't-know response."""
    if not reply:
        return False
    return I_DONT_KNOW_RESPONSE in reply.strip()


def score_summary_length(summary: str, max_words: int = 120) -> bool:
    """Doctor visit summary word count check (maximum 120 words per R6)."""
    if not summary:
        return False
    return len(summary.strip().split()) <= max_words
