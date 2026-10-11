"""Fetch one small page of public, Philippines-eligible Himalayas remote jobs.

The provider's public API allows integrations with attribution and applies its
own rate limits. This importer makes exactly one request per run, keeps only
jobs whose location restrictions explicitly include the Philippines, and does
not assign competency labels or train models.
"""
from datetime import datetime, timezone
import json
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd

from .storage import atomic_bytes

API_URL = "https://himalayas.app/jobs/api/search"
SOURCE_URL = "https://himalayas.app/api"
FEED_PATH = Path("train/remote_feeds/himalayas_ph_jobs.csv")
REPORT_PATH = Path("train/remote_feeds/himalayas_import_report.json")
FIELDS = ["job_id", "job_title", "company", "location", "job_description", "url", "source", "posting_date"]


def fetch_philippines_jobs(root, page=1, timeout=30, request_get=None):
    """Fetch at most one 20-record API page and append explicit PH-eligible rows."""
    if not isinstance(page, int) or page < 1:
        raise ValueError("Page must be a positive integer.")
    if request_get is None:
        def request_get(url, timeout):
            request = Request(url, headers={"User-Agent": "FutureOfWorkResearch/1.0 (attributed public-feed import)"})
            with urlopen(request, timeout=timeout) as response:
                return response.read()

    query = urlencode({"country": "PH", "sort": "recent", "page": page})
    payload = json.loads(request_get(f"{API_URL}?{query}", timeout=timeout))
    jobs = payload.get("jobs", [])
    if not isinstance(jobs, list):
        raise ValueError("Himalayas returned an unexpected jobs response.")

    eligible = []
    for job in jobs[:20]:
        restrictions = job.get("locationRestrictions") or []
        if not any(str(country).strip().casefold() == "philippines" for country in restrictions):
            continue
        job_id = str(job.get("guid") or "").strip()
        title = str(job.get("title") or "").strip()
        description = str(job.get("description") or job.get("excerpt") or "").strip()
        if not job_id or not title or not description:
            continue
        eligible.append({
            "job_id": job_id,
            "job_title": title,
            "company": str(job.get("companyName") or "").strip(),
            "location": "Remote; Philippines",
            "job_description": description,
            "url": str(job.get("applicationLink") or job_id),
            "source": "Himalayas (public remote jobs API)",
            "posting_date": str(job.get("pubDate") or ""),
        })

    root = Path(root)
    feed_path = root / FEED_PATH
    previous = pd.DataFrame(columns=FIELDS)
    if feed_path.exists():
        previous = pd.read_csv(feed_path, dtype=str, keep_default_na=False)
        for field in FIELDS:
            if field not in previous:
                previous[field] = ""
        previous = previous[FIELDS]
    incoming = pd.DataFrame(eligible, columns=FIELDS)
    combined = pd.concat([previous, incoming], ignore_index=True)
    before = len(combined)
    combined = combined.drop_duplicates("job_id", keep="first").reset_index(drop=True)
    added = len(combined) - len(previous.drop_duplicates("job_id"))
    if added:
        atomic_bytes(feed_path, combined.to_csv(index=False).encode("utf-8-sig"))

    report = {
        "fetched_at_utc": datetime.now(timezone.utc).isoformat(),
        "provider": "Himalayas",
        "provider_api": SOURCE_URL,
        "attribution_required": "Credit Himalayas and link each listing's canonical URL when displaying its data.",
        "page": page,
        "response_rows": min(len(jobs), 20),
        "explicit_philippines_eligible_rows": len(eligible),
        "new_rows_added": added,
        "total_saved_rows": len(combined),
        "api_total_count": payload.get("totalCount"),
        "requests_made": 1,
        "training_labels_created": 0,
        "models_trained": 0,
        "feed_file": str(FEED_PATH).replace("\\", "/"),
    }
    atomic_bytes(root / REPORT_PATH, json.dumps(report, indent=2, ensure_ascii=False).encode("utf-8"))
    return report
