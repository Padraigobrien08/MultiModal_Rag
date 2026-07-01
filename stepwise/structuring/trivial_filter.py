"""
Filter out trivial/non-actionable steps that slip through from video outros,
intros, and filler content.
"""
import re

from stepwise.models import Step

# Patterns that indicate a non-actionable step
TRIVIAL_PATTERNS = [
    r"\blike\b.*\bsubscribe\b",
    r"\bsubscribe\b.*\bchannel\b",
    r"\blike\b.*\bvideo\b",
    r"\bthumb(s)? up\b",
    r"\bleave a comment\b",
    r"\bnotification bell\b",
    r"\bhit the bell\b",
    r"\bsmash (the )?like\b",
    r"\bsee you (in the next|next time)\b",
    r"\bthanks? for watching\b",
    r"\bcheck out.*channel\b",
    r"\bfollow (me|us) on\b",
    r"^(intro|outro|introduction|conclusion)$",
]

_compiled = [re.compile(p, re.IGNORECASE) for p in TRIVIAL_PATTERNS]


def _is_trivial(step: Step) -> bool:
    text = f"{step.title} {step.description}".lower()
    return any(p.search(text) for p in _compiled)


def filter_trivial_steps(steps: list[Step]) -> list[Step]:
    """Remove steps with no actionable content (outros, like/subscribe, etc.)."""
    filtered = [s for s in steps if not _is_trivial(s)]
    removed = len(steps) - len(filtered)
    if removed:
        import logging
        logging.getLogger(__name__).info(f"Filtered {removed} trivial step(s)")
    return filtered
