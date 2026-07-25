"""Render a written episode script to speech.

Uses edge-tts (Microsoft neural voices, free). Duration is measured by walking
the MPEG frame headers of the output, which avoids an ffmpeg dependency and
does not rely on the synthesiser emitting word-boundary metadata.
"""
import argparse
import asyncio
import json
import re
import sys

import edge_tts

DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"

# MPEG audio tables, indexed [version_id][bitrate_index] and [version_id][sr_index]
_BITRATES = {
    3: [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0],
    2: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0],
    0: [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0],
}
_RATES = {3: [44100, 48000, 32000], 2: [22050, 24000, 16000], 0: [11025, 12000, 8000]}


def to_speech(md):
    """Strip everything a narrator shouldn't read aloud."""
    md = md.lstrip("﻿")  # BOM would defeat the ^ anchors below
    md = re.sub(r"\A---\n.*?\n---\n", "", md, flags=re.S)  # frontmatter
    md = re.sub(r"```.*?```", "", md, flags=re.S)
    md = re.sub(r"<!--.*?-->", "", md, flags=re.S)
    md = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", md)  # links -> anchor text
    # production notes: [MUSIC], [pause], [SFX] — inline or on their own line
    md = re.sub(r"\[[^\]\n]{0,60}\]", "", md)
    md = re.sub(r"^\s{0,3}#{1,6}\s*", "", md, flags=re.M)
    md = re.sub(r"^\s{0,3}>\s?", "", md, flags=re.M)
    md = re.sub(r"^\s*[-*_]{3,}\s*$", "", md, flags=re.M)
    md = re.sub(r"^\s*[-*+]\s+", "", md, flags=re.M)
    md = re.sub(r"\*\*(.+?)\*\*", r"\1", md, flags=re.S)
    md = re.sub(r"(?<!\w)[*_]([^*_\n]+)[*_](?!\w)", r"\1", md)
    md = md.replace("`", "")
    md = re.sub(r"https?://\S+", "", md)  # a URL read aloud is unlistenable
    md = re.sub(r"[ \t]+", " ", md)
    md = re.sub(r" +([.,;:!?])", r"\1", md)
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def mp3_duration(path):
    """Sum the durations of every MPEG frame in the file."""
    with open(path, "rb") as f:
        data = f.read()
    i, total, n = 0, 0.0, len(data)
    while i < n - 4:
        if data[i] != 0xFF or (data[i + 1] & 0xE0) != 0xE0:
            i += 1
            continue
        h1, h2, h3 = data[i + 1], data[i + 2], data[i + 3]
        ver = (h1 >> 3) & 0x03  # 3=MPEG1, 2=MPEG2, 0=MPEG2.5
        layer = (h1 >> 1) & 0x03  # 1 == Layer III
        br_idx = (h2 >> 4) & 0x0F
        sr_idx = (h2 >> 2) & 0x03
        pad = (h2 >> 1) & 0x01
        if ver == 1 or layer != 1 or br_idx in (0, 15) or sr_idx == 3:
            i += 1
            continue
        bitrate = _BITRATES[ver][br_idx] * 1000
        rate = _RATES[ver][sr_idx]
        samples = 1152 if ver == 3 else 576
        frame_len = int((samples // 8) * bitrate / rate) + pad
        if frame_len <= 4:
            i += 1
            continue
        total += samples / rate
        i += frame_len
    return total


async def render(text, out_path, voice, rate, pitch):
    comm = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    with open(out_path, "wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("script")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--voice", default=DEFAULT_VOICE)
    ap.add_argument("--rate", default="+4%", help="e.g. +8%% for a brisker read")
    ap.add_argument("--pitch", default="+0Hz")
    ap.add_argument("--print-text", action="store_true")
    ap.add_argument("--meta-out", help="write duration/word count as JSON here")
    args = ap.parse_args()

    with open(args.script, encoding="utf-8-sig") as f:
        text = to_speech(f.read())

    if not text:
        print("ERROR: script is empty after cleanup", file=sys.stderr)
        return 1
    if args.print_text:
        print(text)

    asyncio.run(render(text, args.out, args.voice, args.rate, args.pitch))
    secs = mp3_duration(args.out)
    words = len(text.split())
    print(f"voice   : {args.voice} (rate {args.rate})")
    print(f"words   : {words}")
    print(f"duration: {int(secs // 60)}m {int(secs % 60):02d}s")
    if secs:
        print(f"pace    : {words / (secs / 60):.0f} wpm")
    print(f"wrote   : {args.out}")

    if args.meta_out:
        with open(args.meta_out, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "seconds": int(round(secs)),
                    "words": words,
                    "voice": args.voice,
                    "rate": args.rate,
                },
                f,
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
