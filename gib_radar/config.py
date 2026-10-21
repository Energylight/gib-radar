"""Configuration: where the database lives, which CLI profile to use, how to score."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_SKILLS = [
    # Free-form tags Gibwork uses on its own listings.
    "development",
    "engineering",
    "backend",
    "frontend",
    "python",
    "javascript",
    "typescript",
    "node",
    "cli",
    "sdk",
    "mcp",
    "automation",
    "api",
    "integration",
    "bug",
    "testing",
    "qa",
    "3d",
    "blender",
    "three.js",
    "bot",
    "devops",
    "data",
    "script",
]


def _env_path(name: str, default: Path) -> Path:
    raw = os.environ.get(name)
    return Path(raw).expanduser() if raw else default


@dataclass
class Config:
    """Runtime settings. Read from environment, overridable from the CLI."""

    db_path: Path = field(default_factory=lambda: _env_path(
        "GIB_RADAR_DB", Path.home() / ".local/share/gib-radar/radar.db"))
    profile: str = field(default_factory=lambda: os.environ.get("GIB_RADAR_PROFILE", "stage"))
    environment: str = field(
        default_factory=lambda: os.environ.get("GIB_RADAR_ENV", "stage"))
    gibwork_bin: str = field(default_factory=lambda: os.environ.get("GIB_RADAR_GIBWORK", "gibwork"))
    skills: list[str] = field(default_factory=lambda: list(DEFAULT_SKILLS))

    # Scoring weights. Exposed so a user can say "I care about money more
    # than about competition" without editing code.
    weight_pay: float = 1.0
    weight_competition: float = 1.0
    weight_urgency: float = 0.6
    weight_skill: float = 1.2

    def ensure_dirs(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def apply_overrides(self, overrides: dict[str, object]) -> "Config":
        for key, value in overrides.items():
            if value is not None and hasattr(self, key):
                setattr(self, key, value)
        return self

    def as_dict(self) -> dict[str, object]:
        return {
            "db_path": str(self.db_path),
            "profile": self.profile,
            "environment": self.environment,
            "gibwork_bin": self.gibwork_bin,
            "weights": {
                "pay": self.weight_pay,
                "competition": self.weight_competition,
                "urgency": self.weight_urgency,
                "skill": self.weight_skill,
            },
        }


def load_skills_file(path: Path | None) -> list[str]:
    """Read a skills list from a JSON array or a newline-separated file."""
    if path is None or not path.exists():
        return []
    text = path.read_text(encoding="utf-8")
    stripped = text.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        data = json.loads(stripped)
        return [str(x).strip().lower() for x in data if str(x).strip()]
    return [line.strip().lower() for line in text.splitlines()
            if line.strip() and not line.startswith("#")]
