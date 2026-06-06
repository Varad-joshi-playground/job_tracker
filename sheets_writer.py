"""
Google Sheets writer + dedup state management.

- Inserts new jobs at the TOP (row 2), so newest always appears first.
- Marks the first (baseline) run's jobs with "Baseline" in the Source column.
- Maintains seen_urls.json for cross-run dedup (committed back by the workflow).
- Applied? column has a Yes/No dropdown, defaults to No.
"""

import json
import os
from datetime import datetime, timezone
import csv

import gspread
from google.oauth2.service_account import Credentials

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SEEN_FILE = os.path.join(SCRIPT_DIR, "data", "seen_urls.json")

SHEET_ID = os.environ.get("SHEET_ID", "")
WORKSHEET_NAME = "Job Tracker"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADER = ["Date Found", "Company", "Role", "ATS", "Location",
          "Loc Confidence", "Link", "Applied?", "Source"]


def log(msg):
    print(f"{datetime.now().strftime('%H:%M:%S')}  {msg}", flush=True)


# ── Auth ──────────────────────────────────────────────────────────────────────

def get_client():
    """Auth via service-account JSON provided in GOOGLE_CREDENTIALS env (GH secret)."""
    creds_json = os.environ.get("GOOGLE_CREDENTIALS")
    if not creds_json:
        raise RuntimeError("GOOGLE_CREDENTIALS env var not set")
    info = json.loads(creds_json)
    creds = Credentials.from_service_account_info(info, scopes=SCOPES)
    return gspread.authorize(creds)


# ── Dedup state ───────────────────────────────────────────────────────────────

def load_seen():
    if os.path.exists(SEEN_FILE):
        try:
            with open(SEEN_FILE) as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_seen(seen):
    os.makedirs(os.path.dirname(SEEN_FILE), exist_ok=True)
    with open(SEEN_FILE, "w") as f:
        json.dump(sorted(seen), f)


def is_baseline():
    """First-ever run = no seen_urls file yet."""
    return not os.path.exists(SEEN_FILE)


# ── Sheet setup ───────────────────────────────────────────────────────────────

def get_worksheet(client):
    sh = client.open_by_key(SHEET_ID)
    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=20000, cols=len(HEADER))
        ws.update("A1", [HEADER])
        ws.format(f"A1:{chr(64+len(HEADER))}1", {
            "backgroundColor": {"red": 0.12, "green": 0.31, "blue": 0.47},
            "textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
            "horizontalAlignment": "CENTER",
        })
        ws.freeze(rows=1)
        # Applied? dropdown on column H
        sh.batch_update({"requests": [{
            "setDataValidation": {
                "range": {"sheetId": ws.id, "startRowIndex": 1, "endRowIndex": 20000,
                          "startColumnIndex": 7, "endColumnIndex": 8},
                "rule": {"condition": {"type": "ONE_OF_LIST",
                          "values": [{"userEnteredValue": "Yes"}, {"userEnteredValue": "No"}]},
                         "showCustomUi": True, "strict": True},
            }
        }]})
    return ws


# ── Writing (newest at top) ───────────────────────────────────────────────────

def write_jobs(jobs, baseline=False):
    """Insert jobs at the top of the sheet (newest first)."""
    if not jobs:
        log("No new jobs to write.")
        return 0

    client = get_client()
    ws = get_worksheet(client)

    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    source = "Baseline" if baseline else "New"

    rows = [[
        ts, j["company"], j["title"], j["ats"],
        j["location"], j["location_confidence"], j["url"], "No", source,
    ] for j in jobs]

    # Insert in batches to stay under Google Sheets API cell limits
    # (19k rows x 9 cols = 172k cells, well over the 40k per-call limit).
    import time
    BATCH_SIZE = 500
    batches = [rows[i:i+BATCH_SIZE] for i in range(0, len(rows), BATCH_SIZE)]
    log(f"Writing {len(rows)} jobs in {len(batches)} batches of {BATCH_SIZE}...")
    for idx, batch in enumerate(batches, 1):
        ws.insert_rows(batch, row=2, value_input_option="USER_ENTERED")
        log(f"  Batch {idx}/{len(batches)} written ({len(batch)} rows)")
        time.sleep(1.5)

    log(f"Wrote {len(rows)} jobs to sheet ({'baseline' if baseline else 'new'}).")
    
    # Write to CSV in repo as backup
    csv_file = os.path.join(SCRIPT_DIR, "data", "jobs.csv")
    file_exists = os.path.exists(csv_file)
    mode = "a" if file_exists else "w"
    with open(csv_file, mode, newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if not file_exists:
            writer.writerow(HEADER)
        writer.writerows(rows)
    log(f"CSV updated: {csv_file} ({len(rows)} rows appended)")
    return len(rows)
