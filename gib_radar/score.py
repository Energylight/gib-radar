"""Scoring: turn raw task fields into one number a human can argue with.

The formula is intentionally boring and inspectable:

    score = w_pay * pay
          + w_competition * competition
          + w_urgency * urgency
          + w_skill * skill

Every component is normalised to 0..1, and every component's reasons are
returned alongside the score, so a user can see *why* a task ranked high.
Nothing here knows about the network or the store; it is pure data in,
data out, which is what makes it testable.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class ScoreResult:
    score: float
    parts: dict[str, float] = field(default_factory=dict)
    reasons: list[str] = field(default_factory=list)


def pay_component(amount: float | None, cap: float = 1000.0) -> tuple[float, str]:
    """Log-scaled payout. $1 and $10 should differ, $1000 and $5000 barely."""
    if not amount or amount <= 0:
        return 0.0, "no payout listed"
    value = math.log10(1 + amount) / math.log10(1 + cap)
    return min(1.0, value), f"pays ${amount:g}"


def competition_component(submissions: int, max_submissions: int | None,
                          limit: int = 50) -> tuple[float, str]:
    """1.0 when nobody applied, 0.0 when the queue is hopeless.

    When the listing has a fixed number of slots, the share of occupied
    slots matters more than the absolute count: 9/10 is crowded, 9/100 is not.
    """
    subs = max(0, int(submissions or 0))
    if max_submissions:
        fill = subs / max(1, int(max_submissions))
        value = 1.0 - min(1.0, fill)
        return value, f"{subs}/{int(max_submissions)} slots taken"
    value = 1.0 - min(1.0, subs / limit)
    return value, f"{subs} submissions"


def urgency_component(deadline: str | None, now: datetime | None = None) -> tuple[float, str]:
    """Slight bonus for tasks that will close soon but still leave room to work.

    No deadline is neutral (0.5): such listings tend to sit open forever,
    which is neither good nor bad.
    """
    if not deadline:
        return 0.5, "no deadline"
    try:
        dt = datetime.fromisoformat(deadline.replace("Z", "+00:00"))
    except ValueError:
        return 0.5, "deadline unreadable"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    days = (dt - now).total_seconds() / 86400
    if days < 0:
        return 0.0, f"overdue by {abs(days):.1f}d"
    if days <= 1:
        return 0.35, f"{days * 24:.0f}h left — probably too late"
    if days <= 14:
        return 1.0, f"{days:.1f}d left"
    if days <= 45:
        return 0.6, f"{days:.0f}d left"
    return 0.4, f"distant: {days:.0f}d"


def skill_component(tags: list[str], text: str, skills: list[str]) -> tuple[float, str]:
    """Fraction of the user's skills that the listing mentions.

    We match both tags and body text, because Gibwork tags are coarse
    ("Development") while the body names the real stack ("three.js").
    Matching is whole-word: substring matching makes "bot" fire inside
    "bottom", which is how a meme bounty scored as a bot job.
    """
    if not skills:
        return 0.5, "no skills configured"
    haystack = " ".join([*(tags or []), text or ""]).lower()
    hits = [s for s in skills if _mentions(haystack, s.lower())]
    if not hits:
        return 0.0, "no skill match"
    # Three matches already mean "this is for me"; more does not add much.
    value = min(1.0, len(hits) / 3)
    return value, "matches: " + ", ".join(hits[:6])


def _mentions(haystack: str, needle: str) -> bool:
    """Whole-word match for a skill token."""
    if not needle:
        return False
    pattern = r"(?<![a-z0-9])" + re.escape(needle) + r"(?![a-z0-9])"
    return re.search(pattern, haystack) is not None


def score_task(task: dict[str, Any], skills: list[str], weights: dict[str, float],
               now: datetime | None = None) -> ScoreResult:
    amount = _as_float(task.get("amount"))
    pay, pay_reason = pay_component(amount)
    comp, comp_reason = competition_component(
        int(task.get("submissions") or 0), task.get("max_submissions"))
    urg, urg_reason = urgency_component(task.get("deadline"), now)
    tags = task.get("tags") or []
    if isinstance(tags, str):
        tags = [tags]
    skill, skill_reason = skill_component(tags, task.get("content") or "", skills)

    parts = {"pay": pay, "competition": comp, "urgency": urg, "skill": skill}
    total = (
        weights.get("pay", 1.0) * pay
        + weights.get("competition", 1.0) * comp
        + weights.get("urgency", 0.6) * urg
        + weights.get("skill", 1.2) * skill
    )
    normaliser = sum(weights.get(k, 0.0) for k in parts) or 1.0
    score = round(total / normaliser, 4)
    reasons = [pay_reason, comp_reason, urg_reason, skill_reason]
    return ScoreResult(score=score, parts=parts, reasons=reasons)


def _as_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
