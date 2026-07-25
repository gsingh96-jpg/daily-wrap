"""Pull every source feed and emit one compact digest for the curator to read.

Doing this in code rather than making the model fetch 21 feeds keeps the daily
run cheap and predictable. The model's job is judgement, not transport.
"""
import argparse
import concurrent.futures
import datetime as dt
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/126.0 Safari/537.36"
)
ATOM = "{http://www.w3.org/2005/Atom}"

# section -> [(source name, feed url)]
FEEDS = {
    "WORLD": [
        ("BBC World", "https://feeds.bbci.co.uk/news/world/rss.xml"),
        ("Guardian World", "https://www.theguardian.com/world/rss"),
        ("Al Jazeera", "https://www.aljazeera.com/xml/rss/all.xml"),
        ("NPR News", "https://feeds.npr.org/1001/rss.xml"),
    ],
    "BUSINESS": [
        ("CNBC Top", "https://www.cnbc.com/id/100003114/device/rss/rss.html"),
        ("CNBC Markets", "https://www.cnbc.com/id/20910258/device/rss/rss.html"),
        ("BBC Business", "https://feeds.bbci.co.uk/news/business/rss.xml"),
        ("Guardian Business", "https://www.theguardian.com/uk/business/rss"),
        ("MarketWatch", "https://feeds.content.dowjones.io/public/rss/mw_topstories"),
        ("Yahoo Finance", "https://finance.yahoo.com/news/rssindex"),
    ],
    "TECH": [
        ("Ars Technica", "https://feeds.arstechnica.com/arstechnica/index"),
        ("TechCrunch", "https://techcrunch.com/feed/"),
        ("The Verge", "https://www.theverge.com/rss/index.xml"),
        ("Hacker News", "https://news.ycombinator.com/rss"),
        ("MIT Tech Review", "https://www.technologyreview.com/feed/"),
        ("Guardian Tech", "https://www.theguardian.com/uk/technology/rss"),
    ],
    "AUSTRALIA": [
        ("ABC News AU", "https://www.abc.net.au/news/feed/51120/rss.xml"),
        ("ABC AU Business", "https://www.abc.net.au/news/feed/51892/rss.xml"),
        ("Guardian AU", "https://www.theguardian.com/australia-news/rss"),
        ("SMH Business", "https://www.smh.com.au/rss/business.xml"),
        ("AFR", "https://www.afr.com/rss/feed.xml"),
    ],
}

STOP = set(
    """a an the and or but of in on at to for from by with as is are was were be been
    being it its this that these those he she they them his her their we you i not no
    has have had will would could should may might can says say said after before over
    under new more most than then out up down about into against amid ahead who what
    why how when where amid via just also very much many two three first last year years
    day days week weeks month months""".split()
)


def clean(text):
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return re.sub(r"\s+", " ", text).strip()


def parse_when(entry):
    for tag in ("pubDate", "published", ATOM + "published", ATOM + "updated", "updated"):
        raw = entry.findtext(tag)
        if not raw:
            continue
        raw = raw.strip()
        try:
            return parsedate_to_datetime(raw)
        except (TypeError, ValueError):
            pass
        try:
            return dt.datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            pass
    return None


def get_link(entry):
    link = entry.findtext("link")
    if link and link.strip():
        return link.strip()
    for ln in entry.findall(ATOM + "link"):
        if ln.get("rel", "alternate") == "alternate" and ln.get("href"):
            return ln.get("href")
    return ""


def fetch(job):
    section, name, url = job
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=25) as r:
            root = ET.fromstring(r.read())
    except Exception as e:
        print(f"  ! {name}: {type(e).__name__}", file=sys.stderr)
        return []

    entries = root.findall(".//item") or root.findall(f".//{ATOM}entry")
    out = []
    for e in entries[:30]:
        title = clean(e.findtext("title") or e.findtext(ATOM + "title"))
        if not title:
            continue
        summary = clean(
            e.findtext("description")
            or e.findtext(ATOM + "summary")
            or e.findtext(ATOM + "content")
        )
        out.append(
            {
                "section": section,
                "source": name,
                "title": title,
                "summary": summary[:400],
                "link": get_link(e),
                "when": parse_when(e),
            }
        )
    return out


def keywords(title):
    words = re.findall(r"[a-z0-9']+", title.lower())
    return {w for w in words if w not in STOP and len(w) > 2}


def cluster(items):
    """Group near-duplicate headlines. Wide coverage == the day's real story.

    Outlets describe the same event with very different words ("Madrid
    wildfires" vs "200,000 flee as fires sweep France and Spain"), so Jaccard
    over the whole headline is far too strict. Overlap coefficient against the
    shorter headline, with a low floor, matches how these actually vary.
    """
    groups = []
    for item in items:
        kw = keywords(item["title"])
        if len(kw) < 2:
            groups.append([item])
            continue
        best, best_score = None, 0.0
        for g in groups:
            for member in g[:4]:
                mkw = keywords(member["title"])
                if len(mkw) < 2:
                    continue
                shared = len(kw & mkw)
                score = shared / min(len(kw), len(mkw))
                if shared >= 2 and score > best_score:
                    best, best_score = g, score
        if best is not None and best_score >= 0.5:
            best.append(item)
        else:
            groups.append([item])
    return groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=int, default=30, help="max article age")
    ap.add_argument("--out", default="digest.md")
    ap.add_argument("--json-out", default="digest.json")
    args = ap.parse_args()

    jobs = [(sec, n, u) for sec, feeds in FEEDS.items() for n, u in feeds]
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
        batches = list(ex.map(fetch, jobs))

    now = dt.datetime.now(dt.timezone.utc)
    cutoff = now - dt.timedelta(hours=args.hours)
    items, seen_links = [], set()
    for batch in batches:
        for it in batch:
            when = it["when"]
            if when is not None:
                if when.tzinfo is None:
                    when = when.replace(tzinfo=dt.timezone.utc)
                if when < cutoff:
                    continue
                it["age_h"] = round((now - when).total_seconds() / 3600, 1)
            else:
                it["age_h"] = None
            if it["link"] and it["link"] in seen_links:
                continue
            seen_links.add(it["link"])
            items.append(it)

    lines = [
        f"# Raw news digest — generated {now.astimezone().strftime('%A %d %B %Y, %H:%M %Z')}",
        f"\n{len(items)} articles from {len(jobs)} feeds, published within {args.hours}h.\n",
        "Stories are clustered by similarity. A cluster carrying several outlets is a "
        "signal the story is being treated as major — weight that, but judge for yourself.\n",
    ]

    for section in FEEDS:
        sec_items = [i for i in items if i["section"] == section]
        if not sec_items:
            continue
        groups = sorted(cluster(sec_items), key=len, reverse=True)
        lines.append(f"\n## {section}  ({len(sec_items)} articles)\n")
        for g in groups:
            lead = g[0]
            if len(g) > 1:
                srcs = ", ".join(sorted({i["source"] for i in g}))
                lines.append(f"\n### [{len(g)}x — {srcs}] {lead['title']}")
            else:
                lines.append(f"\n### {lead['source']}: {lead['title']}")
            for i in g:
                age = f"{i['age_h']}h ago" if i["age_h"] is not None else "undated"
                lines.append(f"- ({i['source']}, {age}) {i['title']}")
                if i["summary"]:
                    lines.append(f"  > {i['summary']}")
                if i["link"]:
                    lines.append(f"  {i['link']}")

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    for i in items:
        i["when"] = i["when"].isoformat() if i["when"] else None
    with open(args.json_out, "w", encoding="utf-8") as f:
        json.dump(items, f, indent=1, ensure_ascii=False)

    print(f"{len(items)} articles -> {args.out}")


if __name__ == "__main__":
    main()
