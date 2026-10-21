import json

from gib_radar.store import Store, normalise


def sample_task(**overrides):
    task = {
        "id": "task-1",
        "slug": "fix-a-bug",
        "title": "Fix a bug in my app",
        "content": "<p>Fix <strong>this</strong> bug</p>",
        "tags": ["Development"],
        "asset": {"symbol": "USDC", "amount": "10000000", "decimals": 6},
        # Gibwork sends the minimum in human units, unlike asset.amount
        "minSubmissionAmount": "5",
        "deadline": "2026-10-30T00:00:00.000Z",
        "totalSubmissions": 3,
        "maxSubmissions": 10,
        "status": "CREATED",
        "isOpen": True,
        "createdAt": "2026-10-01T00:00:00.000Z",
    }
    task.update(overrides)
    return task


def test_normalise_scales_lamports_to_units():
    row = normalise(sample_task())
    assert row["amount"] == 10.0
    assert row["min_submission"] == 5.0
    assert row["is_open"] == 1
    assert "<p>" not in row["content"]


def test_minimum_is_not_scaled_by_decimals(tmp_path):
    # Regression: dividing minSubmissionAmount by 10**decimals turned a $50
    # minimum into $0.00005.
    row = normalise(sample_task(minSubmissionAmount="50"))
    assert row["min_submission"] == 50.0


def test_block_tags_become_line_breaks():
    row = normalise(sample_task(content="<p>First.</p><p>Second.</p>"))
    assert row["content"] == "First.\nSecond."


def test_upsert_counts_repeat_sightings(tmp_path):
    store = Store(tmp_path / "radar.db")
    assert store.upsert_many([sample_task()]) == 1
    store.upsert_many([sample_task(totalSubmissions=4)])
    found = store.get("task-1")
    assert found["times_seen"] == 2
    assert found["submissions"] == 4
    assert store.stats() == {"tasks": 1, "open": 1}


def test_closed_task_is_not_open(tmp_path):
    store = Store(tmp_path / "radar.db")
    store.upsert_many([sample_task(isOpen=False)])
    assert store.open_tasks() == []


def test_scores_roundtrip(tmp_path):
    store = Store(tmp_path / "radar.db")
    store.upsert_many([sample_task()])
    store.save_score("task-1", 0.5, {"pay": 0.4, "competition": 0.7, "urgency": 1.0, "skill": 0.3},
                     ["выплата $10", "3/10 мест занято"])
    latest = store.latest_scores()
    assert latest["task-1"]["score"] == 0.5
    assert latest["task-1"]["reasons"] == ["выплата $10", "3/10 мест занято"]
    assert json.loads(store.get("task-1")["tags"]) == ["Development"]
