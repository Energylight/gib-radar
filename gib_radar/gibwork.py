"""Thin, testable wrapper around the official `gibwork` CLI.

We do not re-implement the Gibwork protocol. The CLI already handles
authentication, signing, profiles and environments, so the radar treats
it as a data source with a JSON contract:

    gibwork --profile <p> --environment <e> --json task available --page N --limit L

Every call returns the parsed payload or raises GibworkError with the
message the CLI produced. No secrets are read or written here.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from typing import Any


class GibworkError(RuntimeError):
    """The CLI refused, failed, or answered with ok=false."""


@dataclass
class CliResult:
    ok: bool
    data: Any
    stderr: str = ""


class GibworkClient:
    def __init__(self, binary: str = "gibwork", profile: str = "stage",
                 environment: str = "stage", timeout: int = 60) -> None:
        self.binary = binary
        self.profile = profile
        self.environment = environment
        self.timeout = timeout

    def available(self) -> bool:
        """True when the CLI is on PATH and answers --version."""
        if shutil.which(self.binary) is None:
            return False
        try:
            out = self._run(["--version"], json_mode=False)
        except GibworkError:
            return False
        return bool(out.strip())

    # ------------------------------------------------------------------ public
    def list_tasks(self, page: int = 1, limit: int = 50) -> dict[str, Any]:
        payload = self._call([
            "task", "available", "--page", str(page), "--limit", str(limit),
        ])
        if not isinstance(payload, dict):
            raise GibworkError("task available returned a non-object payload")
        return payload

    def get_task(self, task_id: str) -> dict[str, Any]:
        payload = self._call(["task", "get", task_id])
        if isinstance(payload, dict) and "task" in payload:
            payload = payload["task"]
        if not isinstance(payload, dict):
            raise GibworkError("task get returned a non-object payload")
        return payload

    def wallet_address(self) -> str:
        payload = self._call(["wallet", "address"], json_mode=False)
        return payload.strip()

    # ----------------------------------------------------------------- internal
    def _call(self, argv: list[str], json_mode: bool = True) -> Any:
        raw = self._run(argv, json_mode=json_mode)
        if not json_mode:
            return raw
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:  # pragma: no cover - defensive
            raise GibworkError(f"CLI produced invalid JSON: {exc}") from exc
        if isinstance(parsed, dict) and parsed.get("ok") is False:
            err = parsed.get("error") or {}
            raise GibworkError(str(err.get("message") or err or "unknown CLI error"))
        if isinstance(parsed, dict) and "data" in parsed:
            return parsed["data"]
        return parsed

    def _run(self, argv: list[str], json_mode: bool = True) -> str:
        cmd = [self.binary, "--profile", self.profile,
               "--environment", self.environment]
        if json_mode:
            cmd.append("--json")
        cmd.extend(argv)
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=self.timeout,
                check=False,
            )
        except FileNotFoundError as exc:
            raise GibworkError(f"{self.binary} not found on PATH") from exc
        except subprocess.TimeoutExpired as exc:
            raise GibworkError(f"CLI timed out after {self.timeout}s") from exc
        if proc.returncode != 0:
            message = (proc.stderr or proc.stdout or "").strip()
            raise GibworkError(f"CLI exited {proc.returncode}: {message[:400]}")
        return proc.stdout
