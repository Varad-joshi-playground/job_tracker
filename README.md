# Job Tracker

Automated job tracker that pulls AI/ML/data/software roles from **6 ATS platforms**
(Greenhouse, Lever, Ashby, Workday, BambooHR, iCIMS) across ~49k companies, filters
them for relevance, US location, experience level, and visa sponsorship, then writes
new postings to a Google Sheet — newest at the top.

Runs free on **GitHub Actions** every 3 hours. No rate-limiting issues because it
uses official ATS APIs from GitHub's rotating runner IPs.

## How it works

1. Pulls company lists at runtime from the [Feashliaa/job-board-aggregator](https://github.com/Feashliaa/job-board-aggregator) dataset (CC BY-NC 4.0, personal use).
2. Queries each company's official ATS API — one request per company returns all its jobs.
3. Filters every job by:
   - **Relevancy** — domain+role keyword matching (catches "AI Platform Engineer", "Sr. Data Scientist", etc.), management roles excluded
   - **Location** — US only; bare "Remote" kept but flagged `Unverified`; foreign dropped
   - **Experience** — drops roles requiring 6+ years (vague ranges like "2-10 years" kept)
   - **Sponsorship** — drops roles that explicitly offer no visa sponsorship
4. Dedups against `data/seen_urls.json` so you only ever see genuinely new postings.
5. Writes new jobs to the top of your Google Sheet.

The **first run is the baseline** — it captures everything currently open and marks
those rows `Baseline` in the Source column. Every run after only adds jobs that
appeared since the last run (your "new since last check" feed).

## Setup

### 1. Create the Google Sheet + service account

1. Create a blank Google Sheet. Copy its ID from the URL (the part between `/d/` and `/edit`).
2. Go to [console.cloud.google.com](https://console.cloud.google.com) → create a project.
3. Enable **Google Sheets API** and **Google Drive API**.
4. Create a **Service Account** → create a **JSON key** → download it.
   - If your org blocks service-account keys, create the project under a personal Google account instead.
5. Open the downloaded JSON, copy the `client_email` value.
6. Share your Google Sheet with that email address (Editor access).

### 2. Add GitHub repository secrets

In your repo → Settings → Secrets and variables → Actions → New repository secret:

| Secret name | Value |
|---|---|
| `SHEET_ID` | Your Google Sheet ID |
| `GOOGLE_CREDENTIALS` | The **entire contents** of the service-account JSON file |

### 3. Enable Actions

- Push this repo to GitHub (public, so Actions minutes are unlimited).
- Go to the **Actions** tab → enable workflows.
- The first run triggers on schedule, or click **Run workflow** to start the baseline immediately.

## Local testing

```bash
pip install -r requirements.txt
export SHEET_ID="your-sheet-id"
export GOOGLE_CREDENTIALS="$(cat credentials.json)"
python main.py
```

## Tuning

All filters live in `matcher.py`:
- **Add/remove job keywords** → edit `_DOMAIN`, `_ROLE`, `_STANDALONE`
- **Include management roles** → remove `manager`/`director`/`vp` from `_EXCLUDE`
- **Change experience threshold** → edit `EXP_THRESHOLD` (default 6)

Run frequency is in `.github/workflows/scrape.yml` (`cron`). Default is every 3 hours.

Per-platform concurrency (rate-limit safety) is in `scraper.py` `MAX_WORKERS` —
Ashby and BambooHR are kept low intentionally; don't raise them.

## Sheet columns

| Column | Meaning |
|---|---|
| Date Found | When the tracker first saw this job |
| Company | ATS company slug |
| Role | Job title |
| ATS | Which platform it came from |
| Location | Job location |
| Loc Confidence | `US` / `Unverified` (bare Remote or iCIMS) |
| Link | Direct apply URL |
| Applied? | Yes/No dropdown — flip to Yes after applying |
| Source | `Baseline` (first run) or `New` |

## Notes

- **iCIMS** has no location data (sitemap only), so its jobs are always flagged `Unverified`.
- Company lists are cached locally for 7 days, then refreshed from the source repo.
- The workflow commits `seen_urls.json` back to the repo after each run to persist dedup state.

## Credits

Company-discovery dataset from [Feashliaa/job-board-aggregator](https://github.com/Feashliaa/job-board-aggregator) (CC BY-NC 4.0).
