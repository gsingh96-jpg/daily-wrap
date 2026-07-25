"""Fetch article body text so the curator can speak from facts, not headlines.

News sites reject default urllib and tool user-agents, so this presents a
normal browser fingerprint and extracts the paragraph text itself. No third
party dependencies — this has to keep working unattended for months.
"""
import argparse
import concurrent.futures
import gzip
import html
import io
import re
import sys
import urllib.request
import zlib

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-AU,en;q=0.9",
    "Accept-Encoding": "gzip, deflate",
}

DROP_BLOCKS = re.compile(
    r"<(script|style|noscript|svg|figure|aside|nav|header|footer|form)\b.*?</\1>",
    re.S | re.I,
)
BOILERPLATE = re.compile(
    r"^(sign up|subscribe|follow our|get our|read more|related:|advertisement|"
    r"share this|photograph:|image:|by |published |updated |this article|"
    r"we use cookies|enable javascript)",
    re.I,
)


def decompress(raw, encoding):
    if encoding == "gzip":
        return gzip.GzipFile(fileobj=io.BytesIO(raw)).read()
    if encoding == "deflate":
        try:
            return zlib.decompress(raw)
        except zlib.error:
            return zlib.decompress(raw, -zlib.MAX_WBITS)
    return raw


def extract(page):
    page = DROP_BLOCKS.sub(" ", page)
    # Prefer the article body if the page marks one up.
    body = re.search(r"<article\b.*?</article>", page, re.S | re.I)
    scope = body.group(0) if body else page

    paras = []
    for m in re.finditer(r"<p\b[^>]*>(.*?)</p>", scope, re.S | re.I):
        text = re.sub(r"<[^>]+>", "", m.group(1))
        text = html.unescape(text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) < 45 or BOILERPLATE.match(text):
            continue
        paras.append(text)

    # Drop duplicated paragraphs (standfirst repeated in body) preserving order.
    seen, out = set(), []
    for p in paras:
        key = p[:80].lower()
        if key not in seen:
            seen.add(key)
            out.append(p)
    return out


def title_of(page):
    m = re.search(r"<title[^>]*>(.*?)</title>", page, re.S | re.I)
    if not m:
        return ""
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", m.group(1)))).strip()


def fetch(url, max_chars):
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = decompress(r.read(), r.headers.get("Content-Encoding", ""))
            charset = r.headers.get_content_charset() or "utf-8"
        page = raw.decode(charset, errors="replace")
    except Exception as e:
        return url, None, f"{type(e).__name__}: {str(e)[:100]}"

    paras = extract(page)
    if not paras:
        return url, None, "no article text found (likely paywalled or JS-rendered)"

    text, total = [], 0
    for p in paras:
        if total + len(p) > max_chars:
            break
        text.append(p)
        total += len(p)
    return url, (title_of(page), text), None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="+")
    ap.add_argument("--max-chars", type=int, default=4500)
    args = ap.parse_args()

    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda u: fetch(u, args.max_chars), args.urls))

    ok = 0
    for url, payload, err in results:
        print("=" * 78)
        print(f"URL: {url}")
        if err:
            print(f"FAILED: {err}")
            continue
        ok += 1
        title, paras = payload
        print(f"TITLE: {title}\n")
        for p in paras:
            print(p + "\n")
    print("=" * 78)
    print(f"{ok}/{len(results)} fetched", file=sys.stderr)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
