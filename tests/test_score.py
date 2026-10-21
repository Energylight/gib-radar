from datetime import datetime, timedelta, timezone

from gib_radar.score import (
    competition_component,
    pay_component,
    score_task,
    skill_component,
    urgency_component,
)


def test_pay_is_monotonic_and_capped():
    small, _ = pay_component(5)
    big, _ = pay_component(50)
    huge, _ = pay_component(5000)
    assert 0 < small < big <= 1
    assert huge == 1.0


def test_pay_of_nothing_is_zero():
    assert pay_component(None)[0] == 0
    assert pay_component(0)[0] == 0


def test_competition_uses_slots_when_present():
    empty, _ = competition_component(0, 10)
    almost_full, _ = competition_component(9, 10)
    assert empty == 1.0
    assert almost_full < 0.2


def test_competition_without_slots_uses_absolute_count():
    assert competition_component(0, None)[0] == 1.0
    assert competition_component(50, None)[0] == 0.0


def test_urgency_prefers_room_to_work():
    now = datetime(2026, 10, 21, tzinfo=timezone.utc)
    soon = (now + timedelta(days=10)).isoformat()
    tomorrow = (now + timedelta(hours=12)).isoformat()
    long_ago = (now - timedelta(days=1)).isoformat()
    assert urgency_component(soon, now)[0] == 1.0
    assert urgency_component(tomorrow, now)[0] < 0.5
    assert urgency_component(long_ago, now)[0] == 0.0
    assert urgency_component(None, now)[0] == 0.5


def test_skill_matches_tags_and_body():
    value, reason = skill_component(["Development"], "we need a python cli tool", ["python", "cli", "rust"])
    assert value > 0
    assert "python" in reason
    assert skill_component([], "nothing relevant", ["blender"])[0] == 0.0


def test_short_skills_do_not_match_inside_words():
    # "bot" must not fire inside "bottom" — the bug that ranked a meme
    # bounty as a bot job.
    value, reason = skill_component(
        ["Social Media"], "Add TOP/BOTTOM captions at the bottom", ["bot"])
    assert value == 0.0, reason


def test_score_is_normalised():
    task = {
        "amount": 100, "submissions": 2, "max_submissions": 10,
        "deadline": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
        "tags": ["Development"], "content": "python cli",
    }
    result = score_task(task, ["python", "cli"], {"pay": 1, "competition": 1, "urgency": 1, "skill": 1})
    assert 0 <= result.score <= 1
    assert set(result.parts) == {"pay", "competition", "urgency", "skill"}
    assert len(result.reasons) == len(result.parts)


def test_zero_weights_do_not_divide_by_zero():
    result = score_task({"amount": 10}, [], {"pay": 0, "competition": 0, "urgency": 0, "skill": 0})
    assert result.score == 0
