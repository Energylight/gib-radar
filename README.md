# gib-radar

**A terminal radar for Gibwork bounties.** It watches the platform, scores every
open listing, and answers one question: *what is worth doing today?*

Not a website. Not a dashboard. A CLI plus an MCP server, so the answer is
available both to a human in a terminal and to a coding agent that is already
sitting in one.

> Built for the Gibwork Developer Hackathon (non-web use case, CLI/MCP track).

---

## Why this exists

Gibwork's own board tells you what exists. It does not tell you:

- which listing pays enough to be worth a day of work;
- which one already has 90 submissions and no realistic chance;
- which one closes tomorrow;
- which one matches *your* stack, not the platform's average user.

A human solves that by opening tabs and squinting. An agent solves it by
burning context on raw JSON. Both are waste. The radar does the boring part
once, locally, and keeps history the API forgets.

## What it does

```
gib-radar scan      # pull listings through the official Gibwork CLI
gib-radar top       # rank them: pay, competition, deadline, skill match
gib-radar show ID   # full text + score breakdown for one task
gib-radar watch     # same, on a schedule, for a terminal you leave open
```

Every score is four numbers in `[0, 1]`, and every one of them is explained in
plain words:

```
 1. [0.712] Gibwork Developer Hackathon Bounty
    $1000 USDC · 12 submissions · 2026-10-30T21:59:59.000Z
    pays $1000 | 12 submissions | 8.7d left | matches: development, mcp, cli
    id: 1052f22d-3f87-4b1d-b0d7-71a60679e7fa
```

## The formula, in full

```
score = ( w_pay       · pay
        + w_competition · competition
        + w_urgency   · urgency
        + w_skill     · skill ) / (sum of weights)
```

| Component | What it means | Shape |
|---|---|---|
| `pay` | human-unit payout from the listing's `asset` | `log10(1+amount) / log10(1001)`, capped at 1 |
| `competition` | free slots left, not raw submission count | `1 − submissions/max_submissions` (falls back to `1 − subs/50`) |
| `urgency` | room left to actually deliver | `1.0` for 1–14 days, `0.35` under a day, `0` overdue |
| `skill` | overlap between your skills and tags + body text | `min(1, hits/3)` |

Weights are fields on `Config` (`weight_pay`, `weight_competition`,
`weight_urgency`, `weight_skill`), so "I care about money more than about
crowding" is a configuration change, not a patch.

## No dependencies, on purpose

`pyproject.toml` lists zero runtime dependencies. The only external program is
the official `gibwork` CLI, which already owns authentication, signing, profiles
and environments. The radar never sees a private key and never writes one.

The MCP server is hand-rolled JSON-RPC over stdio (~180 lines), so it runs on a
machine that has `python3` and nothing else.

## Install

```bash
git clone <this repo> && cd gib-radar
python3 -m pip install -e .          # or just run from the checkout
gibwork --version                     # the official CLI must be on PATH
```

Point it at your profile if it is not the default one:

```bash
export GIB_RADAR_PROFILE=stage        # or production
export GIB_RADAR_ENV=stage
gib-radar scan
```

## Use it from a coding agent (MCP)

```bash
# register once in any MCP-capable client
gib-radar-mcp        # speaks JSON-RPC 2.0 over stdio
```

Tools exposed:

| Tool | Arguments | Returns |
|---|---|---|
| `radar_top` | `limit`, `min_score` | ranked tasks with score and reasons |
| `radar_scan` | `pages`, `limit` | fetch report (how many fetched/written) |
| `radar_show` | `task_id` | full task + score breakdown |
| `radar_stats` | — | tasks seen / still open |

Smoke test without a client:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | gib-radar-mcp
```

## Layout

```
gib_radar/
  config.py      settings, skills, weights (env-overridable)
  gibwork.py     the only place that shells out to the CLI
  score.py       pure functions: task dict -> number + reasons
  store.py       SQLite: history, raw snapshots, latest scores
  cli.py         scan / top / show / watch / config
  mcp_server.py  stdio MCP server, four tools
tests/           21 tests, no network, no CLI required
demo/demo.sh     a scripted tour for the hackathon video
```

## What the database keeps that the API does not

- `first_seen` / `last_seen` / `times_seen` — a listing that reappears for two
  weeks is a different animal from one posted an hour ago;
- the raw payload of every observation, so a field added by Gibwork later does
  not require a re-fetch to be understood;
- the newest score per task, so ranking never depends on network availability.

## Honest limitations

- **Stage by default.** The public sandbox has few listings; production needs a
  funded wallet profile. Both are one environment variable apart.
- **Keyword skill matching**, not embeddings. Honest, cheap, predictable — and
  the place where a future version earns its keep.
- **Deadline ranking is a heuristic**, not a promise: a task with no deadline is
  scored neutral rather than guessed.
- The radar does not submit work and does not move money. It decides *what* to
  look at; the human still does the work.

## Licence

MIT.
