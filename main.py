"""
Job Tracker - main entry point.

Flow:
  1. Load seen URLs (dedup state)
  2. Scrape 6 ATS platforms, filter for relevant US jobs
  3. Write new jobs to Google Sheet (newest at top, baseline-marked on first run)
  4. Update seen_urls.json (committed back by the GitHub Actions workflow)
"""

import sys

import scraper
import sheets_writer


def main():
    baseline = sheets_writer.is_baseline()
    seen = sheets_writer.load_seen()

    print(f"{'='*60}")
    print(f"JOB TRACKER RUN  |  {'BASELINE' if baseline else 'INCREMENTAL'}")
    print(f"Known URLs: {len(seen):,}")
    print(f"{'='*60}")

    new_jobs = scraper.run(seen)

    if new_jobs:
        sheets_writer.write_jobs(new_jobs, baseline=baseline)
        # Add new URLs to seen-set
        for j in new_jobs:
            seen.add(j["url"])

    sheets_writer.save_seen(seen)
    print(f"Done. Total known URLs now: {len(seen):,}")


if __name__ == "__main__":
    main()
