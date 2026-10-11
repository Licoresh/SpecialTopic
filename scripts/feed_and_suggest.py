"""One bounded daily feed cycle for the Future of Work research app.

Makes at most one free Himalayas API request, stores new Philippines-eligible
remote listings, and generates local BGE-M3 drafts only when new jobs arrive.
It never creates researcher labels or trains a classifier on its own drafts.
"""
import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.config import ROOT
from src.himalayas_feed import fetch_philippines_jobs
from src.pretrained_suggestions import refresh_saved_exact_vocabulary_overrides


def run_cycle(root=ROOT, page=1, progress=print):
    corrected_drafts = refresh_saved_exact_vocabulary_overrides(root)
    feed = fetch_philippines_jobs(root, page=page)
    result = {"feed": feed, "suggestions": None, "corrected_existing_drafts": corrected_drafts}
    if feed["new_rows_added"]:
        from src.unattended_suggestions import run_local_suggestions
        result["suggestions"] = run_local_suggestions(
            root,
            progress=lambda fraction, message: progress(f"{fraction:.0%} {message}"),
        )
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--page", type=int, default=1, help="One API page (20 rows max); default: newest page")
    args = parser.parse_args()
    report = run_cycle(page=args.page, progress=lambda message: print(message, flush=True))
    print(json.dumps(report, indent=2, ensure_ascii=False, default=str), flush=True)


if __name__ == "__main__":
    main()
