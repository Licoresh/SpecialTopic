"""Synthetic scale regression for the aggregated results charts."""
import pandas as pd

from src.analytics import skill_chart_tables
from src.ui import _paginate_frame
from src.visualization import ranked_bar


def test_500_ads_and_93622_phrase_rows_render_compact_aggregated_charts():
    row_count = 93_622
    jobs = pd.DataFrame({"source_id": [f"JOB-{index:03d}" for index in range(500)]})
    skills = pd.DataFrame({
        "source_id": [f"JOB-{index % 500:03d}" for index in range(row_count)],
        "source_type": "jobs",
        "original_phrase": [f"algorithm {index // 500:03d} analysis" for index in range(row_count)],
        "normalized_phrase": [f"algorithm {index // 500:03d} analysis" for index in range(row_count)],
        "competency_category": "Technical / Digital",
        "skill_type": "Technical",
    })

    views = skill_chart_tables(skills, jobs)
    demand = views["chart_skill_demand"]
    figure = ranked_bar(demand, "employer_skill", "employer_demand_count",
                        "Synthetic aggregated demand", limit=30)

    assert len(views["chart_skill_occurrences"]) == row_count
    assert demand.employer_demand_count.sum() == row_count
    assert len(figure.data[0].x) == 30
    assert max(figure.data[0].x) == 500

    first_page, _, page_count = _paginate_frame(views["chart_skill_occurrences"], 1)
    last_page, page_number, _ = _paginate_frame(views["chart_skill_occurrences"], page_count)
    assert page_count == 937 and len(first_page) == 100
    assert page_number == page_count and len(last_page) == 22

    # Generic tool identifiers are unknown objects, not named skills.
    skills["normalized_phrase"] = skills["original_phrase"] = [f"tool {index // 500:03d}" for index in range(row_count)]
    withheld = skill_chart_tables(skills, jobs)
    assert withheld["chart_skill_demand"].empty
    assert len(withheld["chart_phrase_review"]) == row_count
    assert withheld["chart_phrase_review"].review_reason.str.len().gt(0).all()
