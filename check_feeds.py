"""Probe candidate RSS feeds and report which are usable."""
import concurrent.futures
import urllib.request
import xml.etree.ElementTree as ET

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"

FEEDS = {
    # world
    "BBC World": "https://feeds.bbci.co.uk/news/world/rss.xml",
    "Guardian World": "https://www.theguardian.com/world/rss",
    "Al Jazeera": "https://www.aljazeera.com/xml/rss/all.xml",
    "NPR News": "https://feeds.npr.org/1001/rss.xml",
    "AP Top News": "https://rsshub.app/apnews/topics/apf-topnews",
    # business / markets
    "BBC Business": "https://feeds.bbci.co.uk/news/business/rss.xml",
    "CNBC Top": "https://www.cnbc.com/id/100003114/device/rss/rss.html",
    "CNBC Markets": "https://www.cnbc.com/id/20910258/device/rss/rss.html",
    "Guardian Business": "https://www.theguardian.com/uk/business/rss",
    "MarketWatch Top": "https://feeds.content.dowjones.io/public/rss/mw_topstories",
    "Yahoo Finance": "https://finance.yahoo.com/news/rssindex",
    # tech / AI
    "Ars Technica": "https://feeds.arstechnica.com/arstechnica/index",
    "TechCrunch": "https://techcrunch.com/feed/",
    "The Verge": "https://www.theverge.com/rss/index.xml",
    "Hacker News": "https://news.ycombinator.com/rss",
    "MIT Tech Review": "https://www.technologyreview.com/feed/",
    "Guardian Tech": "https://www.theguardian.com/uk/technology/rss",
    # australia
    "ABC News AU": "https://www.abc.net.au/news/feed/51120/rss.xml",
    "ABC AU Business": "https://www.abc.net.au/news/feed/51892/rss.xml",
    "Guardian AU": "https://www.theguardian.com/australia-news/rss",
    "SMH Business": "https://www.smh.com.au/rss/business.xml",
    "AFR": "https://www.afr.com/rss/feed.xml",
}


def probe(item):
    name, url = item
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=20) as r:
            raw = r.read()
            code = r.status
        root = ET.fromstring(raw)
        items = root.findall(".//item") or root.findall(
            ".//{http://www.w3.org/2005/Atom}entry"
        )
        if not items:
            return (name, url, f"HTTP {code} but 0 items", 0, None)
        first = items[0]
        title = first.findtext("title") or first.findtext(
            "{http://www.w3.org/2005/Atom}title"
        )
        return (name, url, "OK", len(items), (title or "").strip()[:90])
    except Exception as e:
        return (name, url, f"FAIL: {type(e).__name__}: {str(e)[:70]}", 0, None)


with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
    results = list(ex.map(probe, FEEDS.items()))

good = [r for r in results if r[2] == "OK"]
bad = [r for r in results if r[2] != "OK"]

print(f"=== USABLE ({len(good)}/{len(results)}) ===")
for name, url, _, n, title in sorted(good):
    print(f"  {name:<20} {n:>3} items | {title}")
print(f"\n=== UNUSABLE ({len(bad)}) ===")
for name, url, status, _, _ in sorted(bad):
    print(f"  {name:<20} {status}")
