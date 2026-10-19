"""Employer demand and cautious employer-framework gap indicators."""
import pandas as pd


def calculate_gaps(skills, jobs, alignment, emerging_min_jobs=2):
    selected = skills[skills.source_id.isin(jobs.source_id)] if not skills.empty and "source_id" in jobs else skills.iloc[:0]
    demand = selected.groupby("normalized_phrase").source_id.nunique() if not selected.empty else pd.Series(dtype=int)
    out = alignment.copy()
    out["employer_demand_count"] = out.normalized_skill.map(demand).fillna(0).astype(int)
    denominator = jobs.source_id.nunique() if "source_id" in jobs else 0
    out["employer_demand_pct"] = out.employer_demand_count / denominator * 100 if denominator else float("nan")
    # Multiple competencies/contexts must not give one phrase extra weight in rates.
    order = {"ALIGNED": 0, "PARTIALLY ALIGNED": 1, "NOT MAPPED": 2, "UNCLASSIFIED": 3}
    phrase_results = out.assign(_rank=out.status.map(order)).sort_values("_rank").drop_duplicates("normalized_skill").drop(columns="_rank")
    mapped = phrase_results.status.isin(["ALIGNED", "PARTIALLY ALIGNED"])
    assessed = phrase_results.status.ne("UNCLASSIFIED")
    rates = {"alignment_rate": float(phrase_results.status.eq("ALIGNED").sum()/mapped.sum()*100) if mapped.any() else None,
             "partially_aligned_rate": float(phrase_results.status.eq("PARTIALLY ALIGNED").sum()/mapped.sum()*100) if mapped.any() else None,
             "unmapped_rate": float(phrase_results.status.eq("NOT MAPPED").sum()/assessed.sum()*100) if assessed.any() else None,
             "mapped_competencies": int(mapped.sum()), "assessed_competencies": int(assessed.sum()),
             "unclassified_count": int(phrase_results.status.eq("UNCLASSIFIED").sum()), "employer_competencies": len(phrase_results),
             "job_ad_denominator": int(denominator)}
    out = out.sort_values(["employer_demand_count", "normalized_skill"], ascending=[False, True])
    unmapped = phrase_results[phrase_results.status.eq("NOT MAPPED")].sort_values("employer_demand_count", ascending=False).copy()
    emerging = unmapped[unmapped.employer_demand_count >= emerging_min_jobs].copy()
    emerging["interpretation"] = "Potential emerging-skill candidate based on repeated demand and no clear mapping; novelty requires human and longitudinal validation."
    return out, unmapped, emerging, rates
