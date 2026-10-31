"""Read-only local benchmark of the analysis pipeline; never publishes research data."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import sys
from time import perf_counter

# Permit `python scripts/benchmark_analysis.py` from the project directory.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd
from src.analytics import accepted_skills, skill_chart_tables
from src.alignment import calculate_mapping, summarize_alignment
from src.cleaning import clean_dataset, duplicate_ids
from src.classification import cached_load_model
from src.job_profile import job_profile_tables
from src.psf_mapping import TaxonomyMatcher
from src.skill_extraction import extract_skills
from src.utils import frame_hash
from src.visualization import ranked_bar


def benchmark(jobs, taxonomy, sizes=(20, 100, 250, 500), *, model=None, max_candidates=300):
    """Measure real functions on copies. Timings are observations, not speed guarantees."""
    if jobs.empty or "source_id" not in jobs:
        raise ValueError("Jobs must contain source_id and at least one advertisement.")
    if any(not isinstance(size, int) or size < 1 for size in sizes):
        raise ValueError("Sample sizes must be positive whole numbers.")
    if not isinstance(max_candidates, int) or max_candidates < 1:
        raise ValueError("max_candidates must be a positive whole number.")
    observations = []
    completed_sizes = set()
    for requested in sizes:
        sample = jobs.head(requested).copy()
        actual = len(sample)
        if actual in completed_sizes:
            continue
        completed_sizes.add(actual)
        timings = {}
        def measure(name, operation):
            start = perf_counter()
            result = operation()
            timings[name] = round(perf_counter() - start, 6)
            print(f"{actual} ads | {name}: {timings[name]:.3f}s", file=sys.stderr, flush=True)
            return result
        start = perf_counter()
        duplicates = measure("duplicate_detection", lambda: duplicate_ids(sample))
        cleaned, _ = measure("cleaning_and_standardization",
                             lambda: clean_dataset(sample, "jobs"))
        matcher = measure("reference_index", lambda: TaxonomyMatcher(taxonomy)) if not taxonomy.empty else None
        extracted, diagnostics = measure("requirement_extraction_and_vocabulary_psf_matching",
            lambda: extract_skills(cleaned, "jobs", matcher=matcher, max_candidates=max_candidates))
        # Production extraction shares phrase discovery and matching. Keep this combined
        # timing honest; do not present it as a pure NLP or pure mapping measurement.
        classification = "skipped: no classifier supplied; no model was trained"
        if model is not None:
            phrases = extracted.normalized_phrase.drop_duplicates().tolist()
            if phrases:
                measure("classifier_inference_only", lambda: model.predict_proba(phrases))
                classification = "inference only; predictions were not applied or evaluated"
            else:
                classification = "skipped: no extracted phrases"
        skills = accepted_skills(extracted)
        mapping = measure("occurrence_psf_alignment", lambda: calculate_mapping(skills, taxonomy))
        def aggregate():
            return {**skill_chart_tables(skills, cleaned), **job_profile_tables(cleaned),
                    "alignment_results": summarize_alignment(mapping)}
        tables = measure("aggregation", aggregate)
        demand = tables["chart_skill_demand"]
        figure = measure("figure_construction_and_json_serialization", lambda: ranked_bar(
            demand, "employer_skill", "employer_demand_count", "Employer-requested skills").to_json())
        observations.append({"requested_ads": requested, "input_rows": actual,
            "retained_unique_ads": int(cleaned.source_id.nunique()),
            "duplicate_candidates": len(duplicates),
            "cleaned_text_characters": int(cleaned.cleaned_text.str.len().sum()),
            "unique_cleaned_texts": int(cleaned.cleaned_text.nunique()),
            "candidate_occurrences": len(extracted),
            "accepted_occurrences": len(skills), "chart_skill_labels": len(demand),
            "discovery_limit_reached_ads": int(diagnostics.get("candidate_limit_reached", pd.Series(dtype=bool)).sum()),
            "classifier": classification, "reference": "local taxonomy" if matcher else "unavailable",
            "figure_json_bytes": len(figure.encode("utf-8")), "stage_seconds": timings,
            "total_measured_seconds": round(perf_counter() - start, 6)})
    return {"measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "source_fingerprint": frame_hash(jobs), "taxonomy_fingerprint": frame_hash(taxonomy),
        "python_version": platform.python_version(),
        "sample_selection": "first N input rows, preserving input order; no representativeness claim",
        "max_candidates": max_candidates,
        "conditions": ["local source files, in-memory copies, no network reads or database writes",
            "all input rows retained; duplicate detection identifies candidates without confirming or removing advertisements",
            "first sample may include cold NLP and plotting initialization; later samples reuse process caches",
            "extraction includes vocabulary classification and PSF scans; alignment is timed separately",
            "classifier inference timing does not change accepted skills or report model quality",
            "file I/O, database transfer, authentication, browser rendering and interactive page load excluded"],
        "observations": observations}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--jobs", type=Path, required=True, help="Local mapped job CSV; original remains unchanged")
    parser.add_argument("--taxonomy", type=Path, help="Local cleaned PSF-AAI CSV")
    parser.add_argument("--sizes", type=int, nargs="+", default=[20, 100, 250, 500])
    parser.add_argument("--max-candidates", type=int, default=300)
    parser.add_argument("--model", type=Path, help="Optional trusted local classifier; never downloaded or trained")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    jobs = pd.read_csv(args.jobs, keep_default_na=False, dtype=str)
    taxonomy = pd.read_csv(args.taxonomy, keep_default_na=False, dtype=str) if args.taxonomy else pd.DataFrame()
    model = cached_load_model(args.model) if args.model else None
    report = benchmark(jobs, taxonomy, args.sizes, model=model, max_candidates=args.max_candidates)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    destination = args.output_dir / "analysis_benchmark.json"
    destination.write_text(json.dumps(report, indent=2), encoding="utf-8")
    rows = []
    for observation in report["observations"]:
        details = {key: value for key, value in observation.items() if key != "stage_seconds"}
        rows.extend(details | {"stage": stage, "seconds": seconds}
                    for stage, seconds in observation["stage_seconds"].items())
    pd.DataFrame(rows).to_csv(args.output_dir / "analysis_benchmark.csv", index=False)
    print(json.dumps({"report": str(destination), "observations": report["observations"]}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
