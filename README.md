# Daily Wrap — private news podcast

A ~10 minute audio news briefing, built every weekday morning at **8:47 Sydney
time** and published as a podcast feed you can subscribe to in any app.

The timing is deliberate: US markets close around 6am AEST, so the episode
covers a complete overnight session and lands before the ASX opens at 10am.

## How a run works

```
fetch_news.py    21 RSS feeds -> digest.md          (~320 articles, clustered)
claude -p        digest.md + brief.md -> script.md  (selection and writing)
fetch_article.py top stories read in full           (called by the curator)
make_episode.py  script.md -> episode.mp3           (edge-tts neural voice)
make_feed.py     GitHub Releases -> feed.xml        (the podcast feed)
```

It runs two ways, from the same scripts:

| | Where | Trigger | Delivery |
|---|---|---|---|
| **Cloud** (primary) | GitHub Actions | `.github/workflows/daily-wrap.yml` | Podcast feed on GitHub Pages |
| **Local** (fallback) | This PC | `Daily News Wrap` scheduled task | `OneDrive\News Podcast\` |

---

## Cloud setup (one time)

**1. Create the repo and push.**

```powershell
gh repo create daily-wrap --public --source . --push
# or, without the gh CLI: create an empty PUBLIC repo on github.com, then
git remote add origin https://github.com/<you>/daily-wrap.git
git push -u origin main
```

The repo must be **public** for GitHub Pages to serve the feed on a free
account, and for podcast apps to fetch it (they can't authenticate).

**2. Add the auth secret.**

```powershell
claude setup-token          # prints a token starting sk-ant-oat01-
gh secret set CLAUDE_CODE_OAUTH_TOKEN
```

That token bills against your Claude subscription. If Anthropic rejects it for
CI use, fall back to an API key instead — the workflow accepts either:

```powershell
gh secret set ANTHROPIC_API_KEY
```

API-key pricing at time of writing: Opus 5 is \$5/\$25 per million tokens in/out
(≈\$1.20 a run), Sonnet 5 is \$3/\$15 (\$2/\$10 introductory through 31 Aug 2026).
To use a cheaper model, set a repo variable: `gh variable set CLAUDE_MODEL --body claude-sonnet-5`.

**3. Turn on Pages.** Repo → Settings → Pages → Source: **GitHub Actions**.

**4. Test it.** `gh workflow run "Daily Wrap"` — then watch with `gh run watch`.

**5. Subscribe.** Once the first run finishes, the feed is at
`https://<you>.github.io/daily-wrap/feed.xml`. Paste that URL into Apple
Podcasts, Pocket Casts, Overcast, or anything else that takes a feed URL.

**6. Retire the local task** (optional, once the cloud run is proven):

```powershell
Disable-ScheduledTask -TaskName "Daily News Wrap"
```

### Scheduling and DST

GitHub cron is UTC, and Sydney switches between UTC+10 and UTC+11. Two crons are
registered — `47 21` and `47 22` — and the `gate` job lets exactly one through by
comparing Sydney's *current* UTC offset against the one each cron was written
for. That's deliberately not a "is it 8am in Sydney?" check, because GitHub
routinely fires cron 5–20 minutes late and a wall-clock test would drop the run.

Treat 8:47 as "around 9". If a run is skipped entirely, check the `gate` job log —
it prints Sydney's offset and which cron it expected.

---

## Files

| File | Purpose |
|---|---|
| `brief.md` | **The editorial brief.** Selection criteria, structure, tone. Edit this to change the show. |
| `fetch_news.py` | Pulls all feeds, clusters near-duplicate headlines, writes `digest.md`. |
| `fetch_article.py` | Fetches article body text with a browser user-agent. Needed because several mastheads block the WebFetch tool. |
| `make_episode.py` | Strips markdown to speakable text, renders MP3, reports true duration. |
| `make_feed.py` | Builds `feed.xml` + landing page from GitHub Releases. |
| `make_cover.py` | Regenerates `cover.png`. Run by hand; not part of the daily job. |
| `run_daily.ps1` | Local orchestrator: run, verify, deliver to OneDrive, notify. |
| `check_feeds.py` | Diagnostic: probes every candidate feed. Run it if a source looks stale. |
| `podcast.json` | Feed metadata (title, author, category). URLs are derived at build time. |

Episodes are **GitHub Releases**, one per day, tagged `ep-YYYY-MM-DD`. The feed is
rebuilt from those releases on every run, so deleting a release removes the
episode from the feed and a half-failed run can never leave the feed pointing at
an MP3 that doesn't exist.

## Changing things

**The editorial line** — edit `brief.md`. That file alone controls what gets
picked, how long the episode runs, and how it sounds. It's written as
instructions to the curator, so plain English changes work.

**Length** — change the word target in `brief.md`. The voice reads at about
160 wpm, so 1,600 words ≈ 10 minutes.

**Voice** — `make_episode.py --voice <name>`; list options with
`python -m edge_tts --list-voices`. Default is `en-US-AndrewMultilingualNeural`;
Australian options include `en-AU-WilliamNeural` and `en-AU-NatashaNeural`. To
change permanently, edit `DEFAULT_VOICE`.

**Sources** — edit the `FEEDS` dict in `fetch_news.py`, then run `check_feeds.py`
to confirm the new feed parses.

**Schedule** — edit the two `cron:` lines in the workflow. Keep both, and keep
them one hour apart, or DST will break the timing half the year.

## Running by hand

```powershell
.\run_daily.ps1                 # full local run
.\run_daily.ps1 -SkipCurate     # re-render an edited script.md
.\run_daily.ps1 -NoDeliver      # build without copying to OneDrive
gh workflow run "Daily Wrap"    # trigger the cloud run now
```

## Known limits

- **Paywalls stay paywalled.** AFR, FT, WSJ, NYT and The Economist are used for
  headline signal only — substance comes from freely-readable outlets. No
  paywall circumvention is attempted.
- **The feed is public.** Anyone with the URL can read it. It's public news read
  aloud, but it is not private.
- **The curator can be wrong.** It writes from what the feeds and articles say.
  Every story in the show notes carries a source link so anything surprising is
  one click from being checked.
- **GitHub cron is approximate** — see the DST note above.
