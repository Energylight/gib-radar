#!/usr/bin/env python3
"""Render a real terminal transcript into a PNG screenshot and an MP4.

Why not a screen recorder: the target machine is Wayland, where frame
capture needs a portal permission dialog and produces 0.75 s frames.
Rendering the *actual* output of a live run is deterministic, legible at
any resolution, and honest about what it is: a transcript, not a camera.

Input:  a text file produced by demo/record.sh (ANSI already stripped).
Output: demo/gib-radar.png (one full frame) and demo/gib-radar.mp4.

    python3 demo/render.py demo/transcript.txt
"""

from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1280, 720
MARGIN = 28
LINE_H = 20
FONT_SIZE = 14
BG = (15, 17, 26)
FG = (219, 222, 235)
DIM = (120, 126, 150)
PROMPT = (126, 231, 135)
ACCENT = (255, 196, 0)
TITLEBAR = (32, 34, 46)

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationMono-Regular.ttf",
    "/usr/share/fonts/truetype/ubuntu/UbuntuMono-R.ttf",
]


def load_font(size: int = FONT_SIZE) -> ImageFont.FreeTypeFont:
    for path in FONT_CANDIDATES:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def wrap(lines: list[str], width: int) -> list[str]:
    out: list[str] = []
    for line in lines:
        while len(line) > width:
            cut = line.rfind(" ", 0, width)
            cut = cut if cut > width // 2 else width
            out.append(line[:cut])
            line = "    " + line[cut:].lstrip()
        out.append(line)
    return out


def classify(line: str) -> tuple[int, int, int]:
    if line.startswith("$ ") or line.startswith("── "):
        return PROMPT
    if re.match(r"^\s*\d+\.\s+\[", line):
        return ACCENT
    if line.startswith("    ") and ("|" in line or "·" in line):
        return DIM
    if not line.strip():
        return DIM
    return FG


def frame(lines: list[str], font: ImageFont.FreeTypeFont, title: str) -> Image.Image:
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    # a thin window chrome, so the image reads as a terminal, not a slide
    d.rectangle([0, 0, W, 34], fill=TITLEBAR)
    for i, color in enumerate([(255, 95, 86), (255, 189, 46), (39, 201, 63)]):
        d.ellipse([16 + i * 22, 11, 28 + i * 22, 23], fill=color)
    d.text((W // 2 - len(title) * 4, 10), title, font=font, fill=DIM)

    y = 52
    max_lines = (H - y - MARGIN) // LINE_H
    visible = lines[-max_lines:]
    for line in visible:
        d.text((MARGIN, y), line, font=font, fill=classify(line))
        y += LINE_H
    return img


def main() -> int:
    src = Path(sys.argv[1] if len(sys.argv) > 1 else "demo/transcript.txt")
    out_dir = src.parent
    raw = src.read_text(encoding="utf-8", errors="replace").splitlines()
    lines = wrap(raw, width=(W - 2 * MARGIN) // 8)
    font = load_font()
    title = "gib-radar — demo"

    # 1. one still: the final state, whole screen
    still = frame(lines, font, title)
    still_path = out_dir / "gib-radar.png"
    still.save(still_path)
    print(f"still: {still_path} ({still.width}x{still.height})")

    # 2. the video: reveal the transcript the way a terminal would
    if shutil.which("ffmpeg") is None:
        print("ffmpeg not found — video skipped")
        return 0
    per_step = max(1, len(lines) // 120)          # ~120 frames total
    frames_dir = Path(tempfile.mkdtemp(prefix="gib-radar-frames-"))
    idx = 0
    for end in range(1, len(lines) + 1, per_step):
        frame(lines[:end], font, title).save(frames_dir / f"f{idx:05d}.png")
        idx += 1
    # hold the last frame for a moment
    for _ in range(12):
        frame(lines, font, title).save(frames_dir / f"f{idx:05d}.png")
        idx += 1

    video = out_dir / "gib-radar.mp4"
    subprocess.run([
        "ffmpeg", "-y", "-loglevel", "error",
        "-framerate", "8", "-i", str(frames_dir / "f%05d.png"),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "20",
        str(video),
    ], check=True)
    print(f"video: {video} ({idx} frames)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
