"""Command line interface: `gib-radar scan | top | show | watch | config`.

The CLI is deliberately plain text with an optional --json mode, because
its two audiences are a human in a terminal and an agent that parses
stdout. No curses, no colours by default, no surprises in a pipe.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

from . import __version__
from .config import Config, load_skills_file
from .gibwork import GibworkClient, GibworkError
from .score import score_task
from .store import Store


# --------------------------------------------------------------------- helpers
def build_config(args: argparse.Namespace) -> Config:
    cfg = Config()
    cfg.apply_overrides({
        "db_path": Path(args.db).expanduser() if getattr(args, "db", None) else None,
        "profile": getattr(args, "profile", None),
        "environment": getattr(args, "environment", None),
        "keypair": Path(args.keypair).expanduser() if getattr(args, "keypair", None) else None,
    })
    extra = load_skills_file(Path(args.skills).expanduser()) if getattr(args, "skills", None) else []
    if extra:
        cfg.skills = sorted({*cfg.skills, *extra})
    return cfg


def weights_of(cfg: Config) -> dict[str, float]:
    return {
        "pay": cfg.weight_pay,
        "competition": cfg.weight_competition,
        "urgency": cfg.weight_urgency,
        "skill": cfg.weight_skill,
    }


def collect(cfg: Config, pages: int, limit: int) -> dict[str, Any]:
    """Pull `pages` pages from the CLI and persist them. Returns a report."""
    client = GibworkClient(cfg.gibwork_bin, cfg.profile, cfg.environment,
                           keypair=cfg.keypair)
    store = Store(cfg.db_path)
    seen: list[dict[str, Any]] = []
    total = 0
    last_page = 1
    for page in range(1, pages + 1):
        payload = client.list_tasks(page=page, limit=limit)
        tasks = payload.get("results") or []
        total = int(payload.get("total") or total)
        last_page = int(payload.get("lastPage") or last_page)
        seen.extend(tasks)
        if page >= last_page:
            break
    written = store.upsert_many(seen)
    scored = rescore(cfg, store)
    return {"fetched": len(seen), "written": written, "scored": scored,
            "total_on_platform": total, "pages": min(pages, last_page)}


def rescore(cfg: Config, store: Store) -> int:
    weights = weights_of(cfg)
    count = 0
    for task in store.open_tasks():
        tags = json.loads(task.get("tags") or "[]")
        result = score_task({**task, "tags": tags}, cfg.skills, weights)
        store.save_score(task["id"], result.score, result.parts, result.reasons)
        count += 1
    return count


def ranked(cfg: Config, store: Store, limit: int, min_score: float) -> list[dict[str, Any]]:
    scores = store.latest_scores()
    rows = []
    for task in store.open_tasks():
        s = scores.get(task["id"])
        if not s:
            continue
        if s["score"] < min_score:
            continue
        rows.append({**task, "score": s["score"], "parts": {
            "pay": s["pay"], "competition": s["competition"],
            "urgency": s["urgency"], "skill": s["skill"],
        }, "reasons": s["reasons"]})
    rows.sort(key=lambda r: r["score"], reverse=True)
    return rows[:limit]


def fmt_money(task: dict[str, Any]) -> str:
    amount = task.get("amount")
    token = task.get("token") or ""
    if amount is None:
        return "—"
    return f"${amount:g} {token}".strip()


def print_table(rows: list[dict[str, Any]]) -> None:
    if not rows:
        print("nothing matches yet — run `gib-radar scan` first")
        return
    for i, r in enumerate(rows, 1):
        print(f"{i:2d}. [{r['score']:.3f}] {r['title']}")
        print(f"    {fmt_money(r)} · {r.get('submissions')} submissions · "
              f"{r.get('deadline') or 'no deadline'}")
        if r["reasons"]:
            print("    " + " | ".join(r["reasons"]))
        print(f"    id: {r['id']}")


# -------------------------------------------------------------------- commands
def cmd_scan(args: argparse.Namespace) -> int:
    cfg = build_config(args)
    cfg.ensure_dirs()
    try:
        report = collect(cfg, args.pages, args.limit)
    except GibworkError as exc:
        print(f"gibwork CLI error: {exc}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(f"fetched {report['fetched']}, stored {report['written']}, "
              f"scored {report['scored']} (platform total: {report['total_on_platform']})")
    return 0


def cmd_top(args: argparse.Namespace) -> int:
    cfg = build_config(args)
    store = Store(cfg.db_path)
    rows = ranked(cfg, store, args.limit, args.min_score)
    if args.json:
        print(json.dumps(rows, ensure_ascii=False, indent=2))
    else:
        print_table(rows)
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    cfg = build_config(args)
    store = Store(cfg.db_path)
    task = store.get(args.task_id)
    if not task:
        print(f"task {args.task_id} is not in the database — run `gib-radar scan`",
              file=sys.stderr)
        return 1
    scores = store.latest_scores().get(args.task_id)
    if args.json:
        print(json.dumps({**task, "score": scores}, ensure_ascii=False, indent=2))
        return 0
    print(task["title"])
    print(f"id:         {task['id']}")
    print(f"pays:       {fmt_money(task)} (min {task.get('min_submission')})")
    print(f"deadline:   {task.get('deadline') or 'none'}")
    print(f"submissions:{task.get('submissions')} of {task.get('max_submissions') or '∞'}")
    print(f"tags:       {task.get('tags')}")
    if scores:
        print(f"score:      {scores['score']:.3f} — " + " | ".join(scores["reasons"]))
    print()
    print((task.get("content") or "")[:1500])
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    cfg = build_config(args)
    cfg.ensure_dirs()
    while True:
        try:
            report = collect(cfg, args.pages, args.limit)
        except GibworkError as exc:
            print(f"[{time.strftime('%H:%M:%S')}] CLI: {exc}", file=sys.stderr)
        else:
            print(f"[{time.strftime('%H:%M:%S')}] scan: {report['fetched']} tasks, "
                  f"{report['written']} stored")
            store = Store(cfg.db_path)
            print_table(ranked(cfg, store, args.top, 0.0))
        if args.once:
            return 0
        time.sleep(args.interval)


def cmd_config(args: argparse.Namespace) -> int:
    cfg = build_config(args)
    print(json.dumps(cfg.as_dict(), ensure_ascii=False, indent=2))
    store = Store(cfg.db_path)
    print(json.dumps(store.stats(), ensure_ascii=False))
    return 0


# ----------------------------------------------------------------------- entry
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="gib-radar",
        description="Gibwork bounty radar: collect, score, rank, serve over MCP.")
    p.add_argument("--version", action="version", version=f"gib-radar {__version__}")
    p.add_argument("--db", help="SQLite path (default ~/.local/share/gib-radar/radar.db)")
    p.add_argument("--profile", help="Gibwork CLI profile (stage/production)")
    p.add_argument("--environment", help="Gibwork CLI environment")
    p.add_argument("--keypair", help="path to a keypair file (needed for production reads)")
    p.add_argument("--skills", help="extra skills file (one per line or a JSON array)")
    sub = p.add_subparsers(dest="command", required=True)

    s = sub.add_parser("scan", help="fetch listings and refresh the database")
    s.add_argument("--pages", type=int, default=3)
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_scan)

    s = sub.add_parser("top", help="show the ranking")
    s.add_argument("--limit", type=int, default=10)
    s.add_argument("--min-score", type=float, default=0.0)
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_top)

    s = sub.add_parser("show", help="full detail for one task")
    s.add_argument("task_id")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_show)

    s = sub.add_parser("watch", help="scan on a schedule")
    s.add_argument("--interval", type=int, default=1800)
    s.add_argument("--pages", type=int, default=2)
    s.add_argument("--limit", type=int, default=50)
    s.add_argument("--top", type=int, default=5)
    s.add_argument("--once", action="store_true")
    s.set_defaults(func=cmd_watch)

    s = sub.add_parser("config", help="show settings and database stats")
    s.set_defaults(func=cmd_config)
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return int(args.func(args) or 0)


if __name__ == "__main__":
    raise SystemExit(main())
