"""gib-radar — a terminal radar for Gibwork bounties.

The tool has one job: turn the firehose of open bounties into a short,
ranked list that a human (or a coding agent over MCP) can act on today.

Design notes
------------
* Zero third-party dependencies. The Gibwork CLI is the only external
  program, and it is already the official way to talk to the platform.
* Everything is local: a SQLite file plus JSONL snapshots. No account
  secrets are stored here; the CLI owns credentials.
* Scoring is explicit and adjustable, not a black box. Every number in a
  ranking can be traced back to a field Gibwork returned.
"""

__version__ = "0.1.0"
