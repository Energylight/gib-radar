#!/usr/bin/env python3
"""Render an explainer video for gib-radar.

The old render.py revealed a raw transcript at 8 fps: ten seconds of dense
terminal text, no captions, no pauses. It was honest and unreadable.

This version keeps the honesty (every line comes from a real run — the
transcripts in demo/) and adds what a viewer needs: a title, a stated problem,
four labelled steps, slow pacing, and colour that points at the numbers that
matter. The MCP scene is a real stdio session, abbreviated and labelled as such.

    python3 demo/explain.py            # -> demo/gib-radar.mp4 + demo/gib-radar.png
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
MARGIN_X = 34
TOP = 58
CAPTION_H = 86
LINE_H = 24
FONT_SIZE = 15
CAPTION_SIZE = 17
FPS = 15

BG = (13, 15, 23)
TITLEBAR = (30, 32, 44)
FG = (222, 226, 240)
DIM = (122, 129, 156)
PROMPT = (126, 231, 135)
ACCENT = (255, 196, 0)
GOOD = (110, 200, 255)
CAPTION_BG = (22, 25, 36)
CAPTION_FG = (236, 239, 247)

MONO = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
]
SANS_BOLD = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]
SANS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
]


def font(candidates, size):
    for p in candidates:
        if Path(p).exists():
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


F_MONO = font(MONO, FONT_SIZE)
F_MONO_BIG = font(MONO, 30)
F_CAP = font(SANS_BOLD, CAPTION_SIZE)
F_SANS = font(SANS, 22)
F_TITLE = font(SANS_BOLD, 54)
F_SUB = font(SANS, 24)


def wrap(text: str, width_px: int, fnt) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        probe = f"{cur} {w}".strip()
        if fnt.getlength(probe) <= width_px:
            cur = probe
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def line_color(line: str):
    s = line.strip()
    if s.startswith("$ "):
        return PROMPT
    if re.match(r"^\s*\d+\.\s+\[", line):
        return ACCENT
    if s.startswith("→") or s.startswith("«"):
        return GOOD
    if s.startswith("id:") or s.startswith("tags:"):
        return DIM
    if not s:
        return DIM
    return FG


def draw_frame(lines: list[str], caption: str, title: str = "gib-radar") -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)

    # window chrome
    d.rectangle([0, 0, W, 34], fill=TITLEBAR)
    for i, c in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([16 + i * 22, 11, 28 + i * 22, 23], fill=c)
    d.text((W // 2 - 40, 9), title, font=F_MONO, fill=DIM)

    # terminal body
    y = TOP
    max_lines = (H - CAPTION_H - TOP - 12) // LINE_H
    for line in lines[-max_lines:]:
        d.text((MARGIN_X, y), line, font=F_MONO, fill=line_color(line))
        y += LINE_H

    # caption bar
    d.rectangle([0, H - CAPTION_H, W, H], fill=CAPTION_BG)
    d.rectangle([0, H - CAPTION_H, W, H - CAPTION_H + 2], fill=(48, 52, 70))
    if caption:
        wrapped = wrap(caption, W - 2 * MARGIN_X, F_CAP)
        cy = H - CAPTION_H + 16
        for cl in wrapped[:2]:
            d.text((MARGIN_X, cy), cl, font=F_CAP, fill=CAPTION_FG)
            cy += 26
    return img


def card(title: str, subtitle: str, bullets: list[str]) -> Image.Image:
    """A full-slide card for the opening and the ending."""
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 8, H], fill=ACCENT)
    y = 150
    d.text((72, y), title, font=F_TITLE, fill=FG)
    y += 84
    d.text((74, y), subtitle, font=F_SUB, fill=DIM)
    y += 78
    for b in bullets:
        d.text((74, y), b, font=F_MONO, fill=GOOD)
        y += 36
    return img


class Frames:
    def __init__(self, out_dir: Path):
        self.dir = out_dir
        self.i = 0
        self.cache: dict[tuple, Path] = {}

    def push(self, img_or_key, img_factory, times: int = 1):
        key = img_or_key
        path = self.cache.get(key)
        if path is None:
            path = self.dir / f"s{len(self.cache):05d}.png"
            img_factory().save(path)
            self.cache[key] = path
        for _ in range(times):
            (self.dir / f"f{self.i:05d}.png").touch()
            (self.dir / f"f{self.i:05d}.png").unlink()
            shutil.copyfile(path, self.dir / f"f{self.i:05d}.png")
            self.i += 1


def main() -> int:
    root = Path(__file__).resolve().parent.parent
    demo = root / "demo"
    transcript = (demo / "transcript.txt").read_text(encoding="utf-8").splitlines()

    # ---- slice the real transcript into the three CLI scenes -----------------
    scan_out, top_out, show_out = [], [], []
    block = scan_out
    for line in transcript:
        if line.startswith("$ "):
            cmd = line[2:].strip()
            m = re.search(r"cli\s+(scan|top|show)\b", cmd)
            if m:
                block = {"scan": scan_out, "top": top_out, "show": show_out}[m.group(1)]
                block.append(line)
                continue
        block.append(line)
    # drop the blank separators at the edges
    def trim(rows):
        while rows and not rows[0].strip():
            rows.pop(0)
        while rows and not rows[-1].strip():
            rows.pop()
        return rows
    scan_out, top_out, show_out = trim(scan_out), trim(top_out), trim(show_out)

    # keep the show scene readable: header block only
    show_cut = []
    for line in show_out:
        show_cut.append(line)
        if line.startswith("tags:"):
            break
    show_cut.append("…  full brief, requirements, What to Submit")

    # ---- the MCP scene -------------------------------------------------------
    mcp_i = next(i for i, l in enumerate(transcript)
                 if l.startswith("$ ") and "mcp_server" in l)
    top_json = json.loads(json.loads(transcript[mcp_i + 1])["result"]["content"][0]["text"])
    mcp_lines = [
        "$ printf '%s\\n' '{\"jsonrpc\":\"2.0\",\"id\":1,\"method\":\"tools/call\",…}' \\",
        "    | gib-radar-mcp",
        '  {"name":"radar_top","arguments":{"limit":2}}',
        "",
    ]
    for t in top_json["tasks"]:
        title = t["title"].strip()
        if len(title) > 38:
            title = title[:37].rstrip() + "…"
        mcp_lines.append(
            f"→ {t['score']:.3f}  ${t['amount']:.0f} {t['token']:<6} "
            f"{t['submissions']:>3} subs   {title}")
    mcp_lines.append("")
    mcp_lines.append("  (abbreviated: the JSON also carries id, deadline, tags, reasons)")

    tmp = Path(tempfile.mkdtemp(prefix="gib-radar-frames-"))
    fr = Frames(tmp)

    def still(lines, caption, times=1):
        key = (tuple(lines), caption)
        fr.push(key, lambda: draw_frame(lines, caption), times)

    # ---- 1. title ------------------------------------------------------------
    title_card = card(
        "gib-radar",
        "a terminal radar for Gibwork bounties",
        ["the board answers: what exists",
         "the radar answers: what is worth doing today",
         "CLI + MCP · no web app · no dependencies"])
    fr.push(("card", "title"), lambda: title_card, 3 * FPS)

    # ---- 2. the problem ------------------------------------------------------
    problem = card(
        "1,460 USDC open",
        "and no answer to the only question that matters",
        ["$1000 or $5?        12 rivals or 237?",
         "two days left or five weeks?   my stack or design?",
         "people open tabs. agents pull raw JSON."])
    fr.push(("card", "problem"), lambda: problem, 4 * FPS)

    # ---- 3. scan -------------------------------------------------------------
    lines: list[str] = []
    cmd = "$ gib-radar scan --pages 1 --limit 50"
    cap1 = "1/4 · collect: the official Gibwork CLI is the only door to the platform"
    for i in range(1, len(cmd) + 1):
        still(lines + [cmd[:i]], cap1, 1)
    still(lines + [cmd], cap1, FPS)
    lines = lines + [cmd]
    for out_line in scan_out[1:]:
        lines = lines + [out_line]
        still(lines, cap1, FPS)
    still(lines, "1/4 · collect: five listings, history in SQLite — the platform forgets it", 2 * FPS)

    # ---- 4. top --------------------------------------------------------------
    cmd = "$ gib-radar top --limit 5"
    cap2 = "2/4 · score: payout, competition, deadline, skill match"
    base = lines + [""]
    for i in range(1, len(cmd) + 1):
        still(base + [cmd[:i]], cap2, 1)
    still(base + [cmd], cap2, FPS)
    shown = base + [cmd]
    for out_line in top_out[1:]:
        shown = shown + [out_line]
        still(shown, cap2, max(1, FPS // 2))
    still(shown, "2/4 · the weights live in config: money, crowding, time, stack", 2 * FPS)

    # ---- 5. show -------------------------------------------------------------
    cmd = "$ gib-radar show 1052f22d-3f87-4b1d-b0d7-71a60679e7fa"
    cap3 = "3/4 · read the brief without opening a browser"
    base: list[str] = []          # clear the screen, the way a terminal would
    for i in range(1, len(cmd) + 1):
        still(base + [cmd[:i]], cap3, 1)
    still(base + [cmd], cap3, FPS)
    shown2 = base + [cmd]
    for out_line in show_cut:
        shown2 = shown2 + [out_line]
        still(shown2, cap3, max(1, FPS // 2))
    still(shown2, "3/4 · the full bounty text sits next to the ranking", 2 * FPS)

    # ---- 6. MCP --------------------------------------------------------------
    cap4 = "4/4 · the same ranking for an agent: stdio JSON-RPC, no SDK, no dependencies"
    shown3: list[str] = []
    for out_line in mcp_lines:
        shown3 = shown3 + [out_line]
        still(shown3, cap4, max(1, FPS // 2))
    still(shown3, "4/4 · four tools: top, scan, show, stats", 3 * FPS)

    # ---- 7. end --------------------------------------------------------------
    end_card = card(
        "github.com/Energylight/gib-radar",
        "21 tests · 0 dependencies · python3 and that is it",
        ["scoring is a pure function; the formula is readable",
         "two bugs found by running it, not by imagining them",
         "next step: embedding-based skill matching"])
    fr.push(("card", "end"), lambda: end_card, 5 * FPS)

    # ---- encode --------------------------------------------------------------
    video = demo / "gib-radar.mp4"
    poster = demo / "gib-radar.png"
    draw_frame(shown, "2/4 · score: payout, competition, deadline, skill match").save(poster)

    if shutil.which("ffmpeg") is None:
        print("ffmpeg не найден")
        return 1
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", str(FPS), "-i", str(tmp / "f%05d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
        "-movflags", "+faststart",
        str(video),
    ], check=True)
    print(f"video: {video}  кадров: {fr.i}  {fr.i / FPS:.1f} c")
    print(f"poster: {poster}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
