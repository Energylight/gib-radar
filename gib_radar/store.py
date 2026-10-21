"""Local SQLite store for observed tasks.

The store keeps two things a live API does not: history (`first_seen`,
`last_seen`, `times_seen`) and a place to hang derived fields (score,
score parts) without re-fetching. Snapshots of the raw payload are kept
as JSON text so nothing is lost when Gibwork adds fields.
"""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator


SCHEMA = """
CREATE TABLE IF NOT EXISTS tasks (
    id                TEXT PRIMARY KEY,
    slug              TEXT,
    title             TEXT NOT NULL,
    content           TEXT,
    tags              TEXT,            -- JSON array
    token             TEXT,            -- USDC / SOL / USDG ...
    amount            REAL,            -- human units, not lamports
    min_submission    REAL,
    deadline          TEXT,            -- ISO or NULL
    submissions       INTEGER,         -- how many already submitted
    max_submissions   INTEGER,
    status            TEXT,
    is_open           INTEGER,
    created_at        TEXT,
    first_seen        TEXT NOT NULL,
    last_seen         TEXT NOT NULL,
    times_seen        INTEGER NOT NULL DEFAULT 1,
    raw               TEXT             -- original JSON payload
);
CREATE INDEX IF NOT EXISTS idx_tasks_open ON tasks(is_open, deadline);

CREATE TABLE IF NOT EXISTS scores (
    task_id     TEXT NOT NULL,
    computed_at TEXT NOT NULL,
    score       REAL NOT NULL,
    pay         REAL,
    competition REAL,
    urgency     REAL,
    skill       REAL,
    reasons     TEXT,                  -- JSON array of human-readable strings
    PRIMARY KEY (task_id, computed_at)
);
"""


def utcnow() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class Store:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._conn() as c:
            c.executescript(SCHEMA)

    @contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        finally:
            conn.close()

    # ------------------------------------------------------------------ writes
    def upsert_many(self, tasks: Iterable[dict[str, Any]]) -> int:
        """Insert or refresh tasks. Returns the number of rows written."""
        now = utcnow()
        written = 0
        with self._conn() as c:
            for task in tasks:
                row = normalise(task)
                existing = c.execute(
                    "SELECT times_seen FROM tasks WHERE id = ?", (row["id"],)
                ).fetchone()
                if existing:
                    c.execute(
                        """UPDATE tasks SET slug=?, title=?, content=?, tags=?, token=?,
                           amount=?, min_submission=?, deadline=?, submissions=?,
                           max_submissions=?, status=?, is_open=?, created_at=?,
                           last_seen=?, times_seen=times_seen+1, raw=?
                           WHERE id=?""",
                        (row["slug"], row["title"], row["content"], row["tags"],
                         row["token"], row["amount"], row["min_submission"],
                         row["deadline"], row["submissions"], row["max_submissions"],
                         row["status"], row["is_open"], row["created_at"], now,
                         row["raw"], row["id"]),
                    )
                else:
                    c.execute(
                        """INSERT INTO tasks (id, slug, title, content, tags, token,
                           amount, min_submission, deadline, submissions,
                           max_submissions, status, is_open, created_at,
                           first_seen, last_seen, times_seen, raw)
                           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (row["id"], row["slug"], row["title"], row["content"],
                         row["tags"], row["token"], row["amount"],
                         row["min_submission"], row["deadline"], row["submissions"],
                         row["max_submissions"], row["status"], row["is_open"],
                         row["created_at"], now, now, 1, row["raw"]),
                    )
                written += 1
        return written

    def save_score(self, task_id: str, score: float, parts: dict[str, float],
                   reasons: list[str]) -> None:
        with self._conn() as c:
            c.execute(
                """INSERT OR REPLACE INTO scores
                   (task_id, computed_at, score, pay, competition, urgency, skill, reasons)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (task_id, utcnow(), score, parts.get("pay"),
                 parts.get("competition"), parts.get("urgency"),
                 parts.get("skill"), json.dumps(reasons, ensure_ascii=False)),
            )

    # ------------------------------------------------------------------- reads
    def open_tasks(self) -> list[dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute("SELECT * FROM tasks WHERE is_open = 1").fetchall()
        return [dict(r) for r in rows]

    def get(self, task_id: str) -> dict[str, Any] | None:
        with self._conn() as c:
            row = c.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
        return dict(row) if row else None

    def latest_scores(self) -> dict[str, dict[str, Any]]:
        with self._conn() as c:
            rows = c.execute(
                """SELECT s.* FROM scores s
                   JOIN (SELECT task_id, MAX(computed_at) AS ts FROM scores GROUP BY task_id) m
                     ON s.task_id = m.task_id AND s.computed_at = m.ts"""
            ).fetchall()
        out: dict[str, dict[str, Any]] = {}
        for r in rows:
            item = dict(r)
            item["reasons"] = json.loads(item.get("reasons") or "[]")
            out[item["task_id"]] = item
        return out

    def stats(self) -> dict[str, int]:
        with self._conn() as c:
            total = c.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]
            open_ = c.execute("SELECT COUNT(*) FROM tasks WHERE is_open = 1").fetchone()[0]
        return {"tasks": total, "open": open_}


def normalise(task: dict[str, Any]) -> dict[str, Any]:
    """Flatten a Gibwork task payload into store columns."""
    asset = task.get("asset") or {}
    decimals = int(asset.get("decimals") or 0)
    raw_amount = asset.get("amount")
    amount = _scaled(raw_amount, decimals)
    # NOTE: minSubmissionAmount arrives in human units ("50" = $50), while
    # asset.amount arrives in base units and must be scaled by decimals.
    # Mixing the two conventions turned a $50 minimum into $0.00005.
    min_raw = task.get("minSubmissionAmount")
    tags = task.get("tags") or []
    return {
        "id": str(task.get("id") or ""),
        "slug": task.get("slug"),
        "title": task.get("title") or "(untitled)",
        "content": _strip_html(task.get("content") or ""),
        "tags": json.dumps(tags, ensure_ascii=False),
        "token": asset.get("symbol") or asset.get("mintAddress"),
        "amount": amount,
        "min_submission": _plain(min_raw),
        "deadline": task.get("deadline"),
        "submissions": int(task.get("totalSubmissions") or 0),
        "max_submissions": task.get("maxSubmissions"),
        "status": task.get("status"),
        "is_open": 1 if task.get("isOpen") else 0,
        "created_at": task.get("createdAt"),
        "raw": json.dumps(task, ensure_ascii=False),
    }


def _plain(value: Any) -> float | None:
    """A number that is already in human units."""
    if value is None or value == "":
        return None
    try:
        return round(float(value), 6)
    except (TypeError, ValueError):
        return None


def _scaled(value: Any, decimals: int) -> float | None:
    if value is None or value == "":
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if decimals:
        number = number / (10 ** decimals)
    return round(number, 6)


BLOCK_TAGS = ("</p>", "</li>", "</h1>", "</h2>", "</h3>", "</h4>",
              "<br>", "<br/>", "<br />", "</div>", "</tr>")


def _strip_html(text: str) -> str:
    """Cheap tag strip with paragraph breaks: enough for search and previews.

    Dropping tags without inserting a break glued sentences together
    ("...web applications.Bounty DescriptionThe selected participants..."),
    which made `show` unreadable even though the text was all there.
    """
    for tag in BLOCK_TAGS:
        text = text.replace(tag, "\n")
    out, depth = [], 0
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(0, depth - 1)
        elif depth == 0:
            out.append(ch)
    lines = [" ".join(line.split()) for line in "".join(out).splitlines()]
    return "\n".join(line for line in lines if line).strip()
