# Submission — Gibwork Developer Hackathon Bounty

**Project:** `gib-radar` — a terminal radar for Gibwork bounties
**Track:** non-web-app use case built on the Gibwork CLI / SDK / MCP
**Repo:** https://github.com/Energylight/gib-radar
**Demo:** [`demo/gib-radar.mp4`](demo/gib-radar.mp4) ·
[`demo/gib-radar.png`](demo/gib-radar.png) ·
[`demo/transcript.txt`](demo/transcript.txt) (the raw output the video was rendered from)

---

## 1. What problem it solves

Gibwork's board answers *what exists*. It does not answer *what is worth doing
today*, which is the only question a freelancer or a coding agent actually has:

- pays $1000, or pays $5?
- twelve submissions or two hundred and two?
- closes in two days or in five weeks?
- matches my stack, or is a design contest?

A person answers that by opening tabs. An agent answers it by pulling raw JSON
into its context window and burning tokens on prose it will never use. Both are
waste, and neither leaves a trace: the next session starts from zero.

`gib-radar` answers it in one line, keeps the history, and serves the same
answer to an agent over MCP — no browser, no dashboard, no account.

## 2. How Gibwork is used (the core, not a wrapper)

The tool does not re-implement the protocol. It treats the official CLI as the
only door to the platform and builds the missing intelligence around it:

| Layer | Gibwork surface | Used for |
|---|---|---|
| discovery | `gibwork task available --page --limit --json` | every scan; the radar never talks to the API directly |
| detail | `gibwork task get <id>` | fetch one listing on demand |
| identity | `gibwork wallet address` | confirm which wallet the profile signs with |
| agent access | `@gibwork/mcp` conventions | the radar exposes its own stdio MCP server so an agent can ask for the ranking without a shell |
| profiles | `--profile`, `--environment`, `--keypair` | stage for development, production for the live board |

Every command the radar runs is visible in `gib_radar/gibwork.py`. No private
key is read, stored, or logged — the CLI keeps that responsibility, and this is
deliberate: a tool that ranks work should not also be a tool that holds money.

## 3. Why it is not a web app

There is no server, no frontend, no browser-based product. Output is stdout;
state is a SQLite file; the interface is a CLI plus JSON-RPC over stdin/stdout.
It runs over SSH, inside CI, in a terminal multiplexer, or under an agent that
has no screen at all.

## 4. What it does, concretely

```
$ gib-radar scan --pages 1 --limit 50
fetched 5, stored 5, scored 5 (platform total: 5)

$ gib-radar top --limit 5
 1. [0.937] Gibwork Developer Hackathon Bounty
    $1000 USDC · 12 submissions · 2026-10-30T04:00:00.000Z
    pays $1000 | 12 submissions | 8.7d left | matches: development, backend, frontend, cli, sdk, mcp
    id: 1052f22d-3f87-4b1d-b0d7-71a60679e7fa
 2. [0.454]  Share Your Side of BASIS Pick ONE Theme
    $150 USDC · 202 submissions · 2026-10-24T00:00:00.000Z
    pays $150 | 202 submissions | 2.5d left | matches: bot
    id: e2575247-1d22-4157-9885-6e52ac5dab36
 3. [0.386] Create a UGC Video Bounty for the Gibwork Mobile App
    $300 USDC · 48 submissions · 2026-10-30T04:00:00.000Z
    pays $300 | 48 submissions | 8.7d left | no skill match
    id: 5f073804-bb43-49c9-99c0-3fb498180465
```

Four components, each in `[0, 1]`, each explainable in one phrase:

- **pay** — `log10(1 + amount) / log10(1001)`, capped. $1 and $10 differ; $1000
  and $5000 barely do.
- **competition** — free slots, not raw submissions: `1 − subs/max_subs`.
  Nine submissions on a ten-slot listing is not the same as nine on a thousand.
- **urgency** — room to deliver: full score for one to fourteen days, `0.35` under
  a day, zero when overdue, neutral when the listing has no deadline.
- **skill** — whole-word overlap between the user's skills and the listing's tags
  plus body text.

Weights live on `Config`, so "money matters more to me than crowding" is a
setting, not a patch.

## 5. What is stored that the platform forgets

- `first_seen` / `last_seen` / `times_seen` — a listing that keeps reappearing is
  a different animal from one posted an hour ago;
- the raw JSON of every observation, so a field Gibwork adds later can be read
  without a re-fetch;
- the newest score per task, so ranking works offline and never depends on the
  network being up at the moment you ask.

## 6. Agent integration (MCP)

`gib-radar-mcp` speaks JSON-RPC 2.0 over stdio and exposes four tools:

| Tool | Purpose |
|---|---|
| `radar_top` | ranked tasks with score and reasons |
| `radar_scan` | refresh from the platform, return a fetch report |
| `radar_show` | one task in full, with the score taken apart |
| `radar_stats` | how many seen, how many still open |

The server is hand-written (~180 lines) with no SDK and no dependencies, so it
runs anywhere `python3` exists. Handshaking, `notifications/*`, unknown methods
and parse errors are all handled — an agent never hangs on silence.

## 7. Verification

- **21 tests, all green**, no network and no CLI required
  (`python3 -m pytest -q`).
- **Live run against production**: 5 listings fetched, scored, ranked; the
  hackathon itself sorts to the top with `0.937`.
- **Two real bugs found by running it, not by reading it**:
  - substring skill matching made `bot` fire inside `bottom`, ranking a meme
    bounty as bot work — fixed with whole-word matching, regression test added;
  - `minSubmissionAmount` arrives in human units while `asset.amount` arrives in
    base units; scaling both turned a $50 minimum into $0.00005 — fixed, test added.

Both are in the transcript and in the commit history.

## 8. Honest limitations

- Skill matching is keyword-based, not semantic. Cheap and predictable; the
  obvious next step is embeddings.
- The urgency curve is a heuristic, not a guarantee. No-deadline listings score
  neutral rather than guessed.
- The radar does not submit work and does not move money. It decides what to look
  at; the human still does the work.
- Production reads require a keypair-backed CLI profile; the radar passes the
  path through and never inspects it.

## 9. Setup

```bash
git clone https://github.com/Energylight/gib-radar && cd gib-radar
python3 -m pip install -e .            # or run straight from the checkout
gibwork --version                      # official CLI must be on PATH

export GIB_RADAR_PROFILE=stage         # or production
export GIB_RADAR_ENV=production
export GIB_RADAR_KEYPAIR=~/.config/gibwork/stage-id.json

gib-radar scan && gib-radar top
```

Demo regeneration: `bash demo/record.sh` — runs the real commands, captures a
transcript, renders the still and the video.

## 10. Roadmap

1. Embedding-based skill matching, keeping the keyword layer as a fast path.
2. Watch mode with desktop notifications when a high-score listing appears.
3. Submission scaffolding: `radar show` already isolates requirements; the next
   step is a checklist and a README skeleton per listing.
4. Shareable score profiles ("I am a 3D generalist", "I do Python automation").
