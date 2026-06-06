"""
Job Tracker - scraper
Fetches jobs from 6 ATS platforms, applies relevancy + US + experience +
sponsorship filters, returns new jobs for the Google Sheet writer.

Company lists are pulled at runtime from the Feashliaa/job-board-aggregator
repo (CC BY-NC 4.0 - personal/non-commercial use) so we don't redistribute
the dataset in this repo.
"""

import json
import os
import random
import re
import time
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from urllib.parse import unquote

import requests

import matcher

# ── Config ────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

# Raw company-list URLs from Feashliaa's repo (pulled at runtime, cached locally)
COMPANY_LIST_URLS = {
    "greenhouse": "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/greenhouse_companies.json",
    "ashby":      "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/ashby_companies.json",
    "bamboohr":   "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/bamboohr_companies.json",
    "lever":      "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/lever_companies.json",
    "workday":    "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/workday_companies.json",
    "icims":      "https://raw.githubusercontent.com/Feashliaa/job-board-aggregator/main/data/icims_companies.json",
}

# Per-platform concurrency (matches Feashliaa's tuned rate-limit-safe values)
MAX_WORKERS = {
    "greenhouse": 30, "lever": 30, "icims": 30,
    "workday": 50, "bamboohr": 10, "ashby": 5,
}

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:147.0) Gecko/20100101 Firefox/147.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:147.0) Gecko/20100101 Firefox/147.0",
]


def log(msg):
    print(f"{datetime.now().strftime('%H:%M:%S')}  {msg}", flush=True)


# ── Company list loading (runtime fetch + local cache) ────────────────────────

def load_company_list(platform: str) -> list:
    """Fetch company list from Feashliaa repo, cache locally for reuse."""
    cache_file = os.path.join(DATA_DIR, f"{platform}_companies.json")

    # Use cache if it exists and is fresh (< 7 days old)
    if os.path.exists(cache_file):
        age_days = (time.time() - os.path.getmtime(cache_file)) / 86400
        if age_days < 7:
            with open(cache_file) as f:
                return json.load(f)

    # Otherwise fetch fresh
    try:
        url = COMPANY_LIST_URLS[platform]
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        companies = resp.json()
        with open(cache_file, "w") as f:
            json.dump(companies, f)
        log(f"  {platform}: fetched {len(companies):,} companies")
        return companies
    except Exception as e:
        log(f"  {platform}: failed to fetch company list ({e})")
        if os.path.exists(cache_file):
            with open(cache_file) as f:
                return json.load(f)
        return []


# ── Per-company fetchers (return list of raw job dicts) ────────────────────────

def _fetch_description(url: str) -> str:
    """Fetch a job page's text for experience/sponsorship filtering."""
    try:
        headers = {"User-Agent": random.choice(USER_AGENTS)}
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 200:
            # crude tag strip; good enough for keyword filters
            text = re.sub(r"<[^>]+>", " ", resp.text)
            return re.sub(r"\s+", " ", text)
    except Exception:
        pass
    return ""


def fetch_greenhouse(slug):
    try:
        url = f"https://boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true"
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            return slug, [], r.status_code
        jobs = []
        for j in r.json().get("jobs", []):
            jobs.append({
                "company": slug, "title": j.get("title", ""),
                "location": (j.get("location") or {}).get("name", ""),
                "url": j.get("absolute_url", ""), "ats": "Greenhouse",
                "content": j.get("content", ""),  # HTML description included
            })
        return slug, jobs, r.status_code
    except Exception:
        return slug, [], None


def fetch_lever(slug):
    try:
        url = f"https://api.lever.co/v0/postings/{slug}"
        r = requests.get(url, timeout=30)
        if r.status_code != 200:
            return slug, [], r.status_code
        jobs = []
        for j in r.json():
            cat = j.get("categories", {})
            jobs.append({
                "company": slug, "title": j.get("text", ""),
                "location": cat.get("location", ""),
                "url": j.get("hostedUrl", ""), "ats": "Lever",
                "content": j.get("descriptionPlain", "") or j.get("description", ""),
            })
        return slug, jobs, r.status_code
    except Exception:
        return slug, [], None


def fetch_ashby(slug):
    try:
        url = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
        payload = {
            "operationName": "ApiJobBoardWithTeams",
            "variables": {"organizationHostedJobsPageName": slug},
            "query": "query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) { jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) { jobPostings { id title locationName } } }",
        }
        headers = {"Content-Type": "application/json", "Accept": "application/json",
                   "User-Agent": random.choice(USER_AGENTS)}
        time.sleep(random.uniform(0.5, 2.0))
        for attempt in range(3):
            r = requests.post(url, json=payload, headers=headers, timeout=30)
            if r.status_code == 200:
                break
            if r.status_code in (429, 503, 502) and attempt < 2:
                time.sleep((2 ** attempt) + random.uniform(0.5, 1.5))
                headers["User-Agent"] = random.choice(USER_AGENTS)
                continue
            return slug, [], r.status_code
        board = (r.json().get("data") or {}).get("jobBoard") or {}
        jobs = []
        for j in board.get("jobPostings") or []:
            jobs.append({
                "company": slug, "title": j.get("title", ""),
                "location": j.get("locationName", ""),
                "url": f"https://jobs.ashbyhq.com/{slug}/{j.get('id')}",
                "ats": "Ashby", "content": "",  # description needs separate fetch
            })
        return slug, jobs, r.status_code
    except Exception:
        return slug, [], None


def fetch_bamboohr(slug):
    try:
        url = f"https://{slug}.bamboohr.com/careers/list"
        time.sleep(random.uniform(0.5, 2.0))
        for attempt in range(3):
            headers = {"Accept": "application/json", "User-Agent": random.choice(USER_AGENTS)}
            r = requests.get(url, timeout=30, headers=headers)
            if r.status_code == 200:
                if "application/json" not in r.headers.get("Content-Type", ""):
                    return slug, [], 404
                jobs = []
                for j in r.json().get("result", []):
                    loc = j.get("location") or {}
                    if isinstance(loc, dict):
                        location = ", ".join(filter(None, [loc.get("city", ""), loc.get("state", "")]))
                    else:
                        location = str(loc) if loc else ""
                    jobs.append({
                        "company": slug, "title": j.get("jobOpeningName", ""),
                        "location": location,
                        "url": f"https://{slug}.bamboohr.com/careers/{j.get('id')}",
                        "ats": "BambooHR", "content": "",
                    })
                return slug, jobs, r.status_code
            if r.status_code in (429, 503, 502) and attempt < 2:
                time.sleep((2 ** attempt) + random.uniform(0.5, 1.5))
                continue
            return slug, [], r.status_code
    except Exception:
        return slug, [], None
    return slug, [], None


def fetch_workday(slug):
    # slug format: "company|wd1|site_id"
    try:
        parts = slug.split("|")
        if len(parts) != 3:
            return slug, [], None
        company, wd, site_id = parts
        wd_num = wd.replace("wd", "")
        base = f"https://{company}.wd{wd_num}.myworkdayjobs.com"
        api = f"{base}/wday/cxs/{company}/{site_id}/jobs"
        headers = {"Accept": "application/json", "Content-Type": "application/json",
                   "User-Agent": random.choice(USER_AGENTS),
                   "Origin": base, "Referer": f"{base}/{site_id}"}
        jobs = []
        offset, limit, observed_total = 0, 20, None
        while True:
            payload = {"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": ""}
            r = requests.post(api, json=payload, headers=headers, timeout=30)
            if r.status_code != 200:
                break
            data = r.json()
            postings = data.get("jobPostings", [])
            total = data.get("total", 0)
            if observed_total is None:
                observed_total = total
            elif total != observed_total:
                break  # Workday truncation/blocking guard
            if not postings:
                break
            for j in postings:
                jobs.append({
                    "company": company, "title": j.get("title", ""),
                    "location": j.get("locationsText", ""),
                    "url": f"{base}/{site_id}{j.get('externalPath', '')}",
                    "ats": "Workday", "content": "",
                })
            offset += limit
            if offset >= total:
                break
            time.sleep(random.uniform(0.3, 1.0))
        return slug, jobs, 200
    except Exception:
        return slug, [], None


def fetch_icims(slug):
    try:
        url = f"https://careers-{slug}.icims.com/sitemap.xml"
        headers = {"Accept": "application/xml", "User-Agent": random.choice(USER_AGENTS)}
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return slug, [], r.status_code
        root = ET.fromstring(r.content)
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        jobs = []
        for loc in root.findall(".//s:url/s:loc", ns):
            ju = (loc.text or "").strip()
            if not ju or "/jobs/" not in ju or ju.endswith("/jobs/intro"):
                continue
            parts = ju.split("/jobs/")[-1].split("/")
            if len(parts) < 2:
                continue
            title = unquote(parts[1]).replace("-", " ").strip().title()
            jobs.append({
                "company": slug, "title": title, "location": "",  # no location from sitemap
                "url": ju, "ats": "iCIMS", "content": "",
            })
        return slug, jobs, r.status_code
    except Exception:
        return slug, [], None


FETCHERS = {
    "greenhouse": fetch_greenhouse, "lever": fetch_lever, "ashby": fetch_ashby,
    "bamboohr": fetch_bamboohr, "workday": fetch_workday, "icims": fetch_icims,
}

# ATS that include description in the list response (can filter exp/sponsorship inline)
HAS_INLINE_CONTENT = {"greenhouse", "lever"}


# ── Filtering pipeline ────────────────────────────────────────────────────────

def process_jobs(raw_jobs, platform):
    """Apply all filters. Returns list of clean job dicts ready for the sheet."""
    out = []
    for job in raw_jobs:
        title = job.get("title", "").strip()
        url = job.get("url", "")
        if not title or not url:
            continue

        # 1. Title relevancy
        if not matcher.title_matches(title):
            continue

        # 2. Location (US filter)
        if platform == "icims":
            # no location data from sitemap
            keep, confidence = True, "Unverified"
        else:
            keep, confidence = matcher.classify_location(job.get("location", ""))
        if not keep:
            continue

        # 3 & 4. Experience + sponsorship (need description text)
        content = job.get("content", "")
        if not content and platform not in HAS_INLINE_CONTENT:
            # Fetch the page for ATS without inline descriptions, but only after
            # title+location already passed (keeps fetch volume low)
            content = _fetch_description(url)

        if content:
            if matcher.is_overqualified(content):
                continue
            if matcher.requires_no_sponsorship(content):
                continue

        out.append({
            "company": job["company"],
            "title": title,
            "location": job.get("location", "") or "Not specified",
            "location_confidence": confidence,
            "url": url,
            "ats": job["ats"],
        })
    return out


def fetch_platform(platform, companies, seen_urls):
    """Fetch + filter all companies for one platform."""
    fetcher = FETCHERS[platform]
    workers = MAX_WORKERS[platform]
    new_jobs = []
    checked = 0

    log(f"[{platform}] checking {len(companies):,} companies ({workers} workers)")
    with ThreadPoolExecutor(max_workers=workers) as ex:
        futures = {ex.submit(fetcher, c): c for c in companies}
        for fut in as_completed(futures):
            checked += 1
            slug, raw, status = fut.result()
            if not raw:
                continue
            # Drop already-seen URLs BEFORE expensive description fetches
            fresh = [j for j in raw if j.get("url") not in seen_urls]
            if not fresh:
                continue
            processed = process_jobs(fresh, platform)
            new_jobs.extend(processed)
            if checked % 500 == 0:
                log(f"[{platform}] {checked:,}/{len(companies):,} checked, {len(new_jobs)} new matches")

    log(f"[{platform}] done: {len(new_jobs)} new matching jobs")
    return new_jobs


def run(seen_urls, platforms=None):
    """Main entry. Returns list of new matching jobs across all platforms."""
    platforms = platforms or list(FETCHERS.keys())
    all_new = []

    # Run platforms concurrently with each other (each manages its own worker pool)
    with ThreadPoolExecutor(max_workers=len(platforms)) as pex:
        futures = {}
        for p in platforms:
            companies = load_company_list(p)
            if companies:
                futures[pex.submit(fetch_platform, p, companies, seen_urls)] = p
        for fut in as_completed(futures):
            all_new.extend(fut.result())

    # Dedup within this run (same URL from multiple sources)
    seen_this_run = set()
    deduped = []
    for j in all_new:
        if j["url"] in seen_this_run:
            continue
        seen_this_run.add(j["url"])
        deduped.append(j)

    log(f"TOTAL new matching jobs this run: {len(deduped)}")
    return deduped
