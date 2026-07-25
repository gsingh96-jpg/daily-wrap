"""Build the podcast RSS feed and landing page from GitHub Releases.

Releases are the source of truth — there is no manifest file to keep in sync,
so deleting a release removes the episode from the feed automatically and a
failed run can never leave the feed describing an MP3 that doesn't exist.

Reads the GitHub releases JSON on stdin:
    gh api repos/{owner}/{repo}/releases --paginate | python make_feed.py --out site
"""
import argparse
import datetime as dt
import html
import json
import os
import re
import sys
import xml.etree.ElementTree as ET

ITUNES = "http://www.itunes.com/dtds/podcast-1.0.dtd"
ATOM = "http://www.w3.org/2005/Atom"
ET.register_namespace("itunes", ITUNES)
ET.register_namespace("atom", ATOM)

# The workflow stamps this into each release body so the feed can report a real
# duration; podcast apps show a blank scrubber without it.
DURATION_RE = re.compile(r"<!--\s*duration_seconds:\s*(\d+)\s*-->")


def load_config(path):
    """Config file, with the URLs overridable from the environment.

    The Pages URL isn't knowable until the repo exists, so the workflow derives
    it from $GITHUB_REPOSITORY rather than making anyone hand-edit JSON.
    """
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    for key, env in (("site_url", "PODCAST_SITE_URL"), ("image_url", "PODCAST_IMAGE_URL")):
        if os.environ.get(env):
            cfg[key] = os.environ[env]
    missing = [k for k in ("title", "description", "author", "email") if not cfg.get(k)]
    if missing:
        raise SystemExit(f"podcast.json is missing: {', '.join(missing)}")
    return cfg


def rfc822(iso):
    when = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    return when.strftime("%a, %d %b %Y %H:%M:%S +0000")


def hhmmss(seconds):
    h, rem = divmod(int(seconds), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def clean_notes(body):
    """Release body -> a description a podcast app can render."""
    body = DURATION_RE.sub("", body or "")
    # Bare URLs on their own line are noise in a player; keep the prose.
    body = re.sub(r"^\s*https?://\S+\s*$", "", body, flags=re.M)
    # Most players show the description as plain text, so markdown emphasis
    # markers read as literal asterisks. Drop them; keep the words.
    body = re.sub(r"\*\*(.+?)\*\*", r"\1", body, flags=re.S)
    body = re.sub(r"^#{1,6}\s*", "", body, flags=re.M)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def sub(parent, tag, text=None, **attrs):
    el = ET.SubElement(parent, tag, {k: str(v) for k, v in attrs.items()})
    if text is not None:
        el.text = text
    return el


def build_feed(cfg, episodes, feed_url):
    # Namespaces come from register_namespace above — setting xmlns:* by hand as
    # well emits each declaration twice, which is not well-formed XML.
    rss = ET.Element("rss", {"version": "2.0"})
    ch = ET.SubElement(rss, "channel")

    sub(ch, "title", cfg["title"])
    sub(ch, "link", cfg["site_url"])
    sub(ch, "description", cfg["description"])
    sub(ch, "language", cfg.get("language", "en-au"))
    sub(ch, "lastBuildDate", rfc822(dt.datetime.now(dt.timezone.utc).isoformat()))
    ET.SubElement(
        ch,
        f"{{{ATOM}}}link",
        {"href": feed_url, "rel": "self", "type": "application/rss+xml"},
    )
    sub(ch, f"{{{ITUNES}}}author", cfg["author"])
    sub(ch, f"{{{ITUNES}}}summary", cfg["description"])
    sub(ch, f"{{{ITUNES}}}explicit", "false")
    sub(ch, f"{{{ITUNES}}}type", "episodic")
    ET.SubElement(ch, f"{{{ITUNES}}}image", {"href": cfg["image_url"]})
    owner = ET.SubElement(ch, f"{{{ITUNES}}}owner")
    sub(owner, f"{{{ITUNES}}}name", cfg["author"])
    sub(owner, f"{{{ITUNES}}}email", cfg["email"])
    cat = ET.SubElement(ch, f"{{{ITUNES}}}category", {"text": "News"})
    ET.SubElement(cat, f"{{{ITUNES}}}category", {"text": "Daily News"})

    for ep in episodes:
        item = ET.SubElement(ch, "item")
        sub(item, "title", ep["title"])
        sub(item, "description", ep["notes"])
        sub(item, f"{{{ITUNES}}}summary", ep["notes"])
        sub(item, "pubDate", rfc822(ep["published_at"]))
        sub(item, "guid", ep["tag"], isPermaLink="false")
        sub(item, "link", ep["html_url"])
        ET.SubElement(
            item,
            "enclosure",
            {"url": ep["audio_url"], "length": str(ep["size"]), "type": "audio/mpeg"},
        )
        if ep["duration"]:
            sub(item, f"{{{ITUNES}}}duration", hhmmss(ep["duration"]))
        sub(item, f"{{{ITUNES}}}explicit", "false")

    return ET.ElementTree(rss)


PAGE = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  :root {{ color-scheme: light dark; --fg:#16181d; --bg:#fbfaf8; --mut:#6b6f76; --line:#e3e0da; --accent:#9c4221; }}
  @media (prefers-color-scheme: dark) {{
    :root {{ --fg:#e8e6e3; --bg:#16181d; --mut:#9aa0a8; --line:#2c3038; --accent:#e08b5f; }}
  }}
  * {{ box-sizing: border-box; }}
  body {{ margin:0; padding:2.5rem 1.25rem 4rem; background:var(--bg); color:var(--fg);
         font:16px/1.65 ui-serif, Georgia, "Times New Roman", serif; }}
  main {{ max-width: 44rem; margin: 0 auto; }}
  h1 {{ font-size: clamp(1.9rem, 5vw, 2.6rem); margin: 0 0 .3rem; letter-spacing: -.02em; }}
  .sub {{ color: var(--mut); margin: 0 0 2rem; }}
  .sub a {{ color: var(--accent); }}
  .feed {{ display:inline-block; margin-bottom:2.5rem; padding:.6rem 1rem; border:1px solid var(--line);
           border-radius:.5rem; text-decoration:none; color:var(--accent); font-family:ui-sans-serif,system-ui,sans-serif;
           font-size:.92rem; }}
  article {{ border-top:1px solid var(--line); padding:1.75rem 0; }}
  h2 {{ font-size:1.15rem; margin:0 0 .35rem; }}
  time {{ color:var(--mut); font-size:.85rem; font-family:ui-sans-serif,system-ui,sans-serif; }}
  audio {{ width:100%; margin:.9rem 0 .5rem; }}
  details summary {{ cursor:pointer; color:var(--mut); font-size:.9rem;
                     font-family:ui-sans-serif,system-ui,sans-serif; }}
  pre {{ white-space:pre-wrap; word-wrap:break-word; font:inherit; margin:.75rem 0 0; }}
  footer {{ margin-top:3rem; color:var(--mut); font-size:.85rem; }}
</style>
</head>
<body><main>
<h1>{title}</h1>
<p class="sub">{description}</p>
<a class="feed" href="feed.xml">Subscribe &mdash; copy this feed URL into any podcast app</a>
{items}
<footer>Built from 21 public news feeds each weekday morning. Paywalled mastheads are used for
headline signal only.</footer>
</main></body>
</html>
"""

ITEM = """<article>
<h2>{title}</h2>
<time>{date}</time>
<audio controls preload="none" src="{audio}"></audio>
<details><summary>Show notes</summary><pre>{notes}</pre></details>
</article>
"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="podcast.json")
    ap.add_argument("--out", default="site")
    ap.add_argument("--max-episodes", type=int, default=60)
    args = ap.parse_args()

    cfg = load_config(args.config)
    # utf-8-sig so a BOM-prefixed pipe (any Windows-side tooling) still parses.
    releases = json.loads(sys.stdin.buffer.read().decode("utf-8-sig") or "[]")

    episodes = []
    for rel in releases:
        if rel.get("draft"):
            continue
        audio = next(
            (a for a in rel.get("assets", []) if a["name"].lower().endswith(".mp3")), None
        )
        if not audio:
            continue  # a run that failed before rendering — skip, don't break the feed
        m = DURATION_RE.search(rel.get("body") or "")
        episodes.append(
            {
                "tag": rel["tag_name"],
                "title": rel["name"] or rel["tag_name"],
                "notes": clean_notes(rel.get("body")),
                "published_at": rel["published_at"],
                "html_url": rel["html_url"],
                "audio_url": audio["browser_download_url"],
                "size": audio["size"],
                "duration": int(m.group(1)) if m else None,
            }
        )

    episodes.sort(key=lambda e: e["published_at"], reverse=True)
    episodes = episodes[: args.max_episodes]

    os.makedirs(args.out, exist_ok=True)
    feed_url = cfg["site_url"].rstrip("/") + "/feed.xml"
    tree = build_feed(cfg, episodes, feed_url)
    tree.write(
        os.path.join(args.out, "feed.xml"), encoding="utf-8", xml_declaration=True
    )

    items = "".join(
        ITEM.format(
            title=html.escape(e["title"]),
            date=dt.datetime.fromisoformat(
                e["published_at"].replace("Z", "+00:00")
            ).strftime("%A %d %B %Y"),
            audio=html.escape(e["audio_url"], quote=True),
            notes=html.escape(e["notes"]),
        )
        for e in episodes
    )
    with open(os.path.join(args.out, "index.html"), "w", encoding="utf-8") as f:
        f.write(
            PAGE.format(
                title=html.escape(cfg["title"]),
                description=html.escape(cfg["description"]),
                items=items or "<p>No episodes published yet.</p>",
            )
        )

    print(f"feed: {len(episodes)} episodes -> {args.out}/feed.xml")


if __name__ == "__main__":
    main()
