"""Minimal MCP server over stdio — no SDK, no dependencies.

Why hand-rolled: the radar must run on the judge's machine with `python3`
and nothing else. MCP's stdio transport is newline-delimited JSON-RPC 2.0,
which is small enough to implement honestly in one file, and the result is
auditable by anyone reading it.

Supported: initialize, ping, tools/list, tools/call, notifications/*.
Everything else gets a proper JSON-RPC error instead of silence.

Try it by hand:

    printf '%s\\n' '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \\
        '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' | gib-radar-mcp
"""

from __future__ import annotations

import json
import sys
from typing import Any, Callable

from . import __version__
from .cli import collect, ranked, rescore
from .config import Config
from .store import Store

PROTOCOL_VERSION = "2025-06-18"
SERVER_NAME = "gib-radar"

TOOLS: list[dict[str, Any]] = [
    {
        "name": "radar_top",
        "description": (
            "Rank open Gibwork bounties by payout, competition, deadline and "
            "skill match. Returns the best tasks with a score and reasons."),
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 5},
                "min_score": {"type": "number", "minimum": 0, "maximum": 1, "default": 0},
            },
        },
    },
    {
        "name": "radar_scan",
        "description": "Fetch fresh listings from Gibwork and update the local database.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pages": {"type": "integer", "minimum": 1, "maximum": 20, "default": 2},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 50},
            },
        },
    },
    {
        "name": "radar_show",
        "description": "Full details for one task by id, including its score breakdown.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
    {
        "name": "radar_stats",
        "description": "How many tasks the radar has seen, and how many are still open.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


class Server:
    def __init__(self, config: Config | None = None) -> None:
        self.config = config or Config()
        self.config.ensure_dirs()
        self.store = Store(self.config.db_path)

    # ------------------------------------------------------------- dispatch
    def handle(self, request: dict[str, Any]) -> dict[str, Any] | None:
        method = request.get("method")
        req_id = request.get("id")
        if method is None:
            return None  # a response, not a request; ignore
        if str(method).startswith("notifications/"):
            return None  # notifications never get a reply

        try:
            if method == "initialize":
                result = {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": __version__},
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": TOOLS}
            elif method == "tools/call":
                params = request.get("params") or {}
                result = self.call_tool(str(params.get("name")), params.get("arguments") or {})
            else:
                return self.error(req_id, -32601, f"method not found: {method}")
        except Exception as exc:  # noqa: BLE001 - a tool must not kill the server
            return self.error(req_id, -32603, f"{type(exc).__name__}: {exc}")
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def call_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        handlers: dict[str, Callable[[dict[str, Any]], Any]] = {
            "radar_top": self.tool_top,
            "radar_scan": self.tool_scan,
            "radar_show": self.tool_show,
            "radar_stats": self.tool_stats,
        }
        if name not in handlers:
            raise ValueError(f"unknown tool: {name}")
        payload = handlers[name](args)
        return {"content": [{"type": "text", "text": json.dumps(payload, ensure_ascii=False, indent=2)}],
                "isError": False}

    # ---------------------------------------------------------------- tools
    def tool_top(self, args: dict[str, Any]) -> Any:
        limit = int(args.get("limit", 5))
        min_score = float(args.get("min_score", 0))
        rescore(self.config, self.store)  # keep scores fresh after weight changes
        rows = ranked(self.config, self.store, limit, min_score)
        return {"count": len(rows), "tasks": [_slim(r) for r in rows]}

    def tool_scan(self, args: dict[str, Any]) -> Any:
        return collect(self.config, int(args.get("pages", 2)), int(args.get("limit", 50)))

    def tool_show(self, args: dict[str, Any]) -> Any:
        task_id = str(args.get("task_id") or "")
        task = self.store.get(task_id)
        if not task:
            raise ValueError(f"task {task_id} not in the local database; run radar_scan first")
        scores = self.store.latest_scores().get(task_id)
        return {"task": task, "score": scores}

    def tool_stats(self, args: dict[str, Any]) -> Any:
        return self.store.stats()

    # ---------------------------------------------------------------- utils
    @staticmethod
    def error(req_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}}


def _slim(row: dict[str, Any]) -> dict[str, Any]:
    """Keep the reply small enough to be useful inside an agent's context."""
    return {
        "id": row["id"],
        "title": row["title"],
        "score": row["score"],
        "amount": row.get("amount"),
        "token": row.get("token"),
        "deadline": row.get("deadline"),
        "submissions": row.get("submissions"),
        "max_submissions": row.get("max_submissions"),
        "tags": json.loads(row.get("tags") or "[]"),
        "reasons": row.get("reasons"),
    }


def main() -> int:
    server = Server()
    out = sys.stdout
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            out.write(json.dumps({"jsonrpc": "2.0", "id": None,
                                  "error": {"code": -32700, "message": "parse error"}}) + "\n")
            out.flush()
            continue
        reply = server.handle(request)
        if reply is not None:
            out.write(json.dumps(reply, ensure_ascii=False) + "\n")
            out.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
