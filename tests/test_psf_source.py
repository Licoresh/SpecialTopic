"""SYNTHETIC DATA — NOT RESEARCH DATA; framework rows use fictional sources."""
import pandas as pd
import pytest
from src.config import FIELDS
from src.psf_source import activate_framework, parse_framework
from src.training_sources import training_taxonomy


def test_range_of_application_extraction_stops_before_pdf_footer():
    from src.psf_source import _range_of_application
    text = "Range of Application\nCloud services may include: • Python • SQL\nAnalytics & Artifical Intelligence 150 Functional Skills and Competencies (FSC)"
    assert _range_of_application(text) == "Cloud services may include: • Python • SQL"


def test_researcher_activation_requires_traceable_source(workspace):
    frame = pd.DataFrame([{
        "competency_id": "SYNTHETIC-CODE-1", "competency_name": "Synthetic framework competency",
        "competency_description": "SYNTHETIC DATA — NOT RESEARCH DATA", "competency_category": "Synthetic category",
        "job_role": "Synthetic analyst", "functional_skill": "Synthetic framework competency",
        "enabling_skill": "", "proficiency_level": "Level 1", "keywords": "", "aliases": "",
        "source_page": "99", "source_url": "https://example.test/synthetic.pdf", "source_hash": "SYNTHETIC-HASH",
        "review_status": "Parsed — needs researcher review"
    }], columns=FIELDS["psf_aai"])
    with pytest.raises(ValueError, match="reviewer"):
        activate_framework(frame, "", workspace)
    with pytest.raises(ValueError, match="unique"):
        bad = pd.concat([frame, frame], ignore_index=True)
        activate_framework(bad, "Synthetic reviewer", workspace)
    verified = activate_framework(frame, "Synthetic reviewer", workspace)
    assert verified.review_status.tolist() == ["Researcher verified"]
    assert verified.reviewer.tolist() == ["Synthetic reviewer"]
    assert training_taxonomy(workspace).competency_name.tolist() == ["Synthetic framework competency"]
    assert pd.read_csv(workspace/"data/processed/verified_psf_aai.csv").source_page.tolist() == [99]


def test_framework_activation_refuses_missing_page_or_url(workspace):
    frame = pd.DataFrame([{"competency_id": "SYNTHETIC-1", "competency_name": "Synthetic competency",
                           "source_page": "", "source_url": "https://example.test"}])
    with pytest.raises(ValueError, match="source page"):
        activate_framework(frame, "Synthetic reviewer", workspace)


def test_official_pdf_parser_retains_competency_codes_pages_and_roles():
    from src.config import ROOT
    path = ROOT / "data/reference/psf_aai_official.pdf"
    if not path.exists():
        pytest.skip("Bundled official PSF-AAI PDF is not present")
    frame, roles = parse_framework(path)
    assert len(frame) == 94
    assert frame.competency_id.str.startswith(("AAI-", "ESC-")).all()
    assert frame.source_page.astype(int).between(1, 315).all()
    assert frame.source_hash.str.fullmatch(r"[0-9a-f]{64}").all()
    cloud = frame.loc[frame.competency_name.eq("Cloud Computing"), "range_of_application"].iloc[0]
    assert "Python" in cloud
    assert frame.range_of_application.str.contains("SQL", case=False).any()
    modeling = frame.loc[frame.competency_name.eq("Computational Modeling"), "competency_description"].iloc[0]
    assert "statistical algorithms" in modeling.casefold()
    assert "skills application" in modeling.casefold()
    from src.psf_mapping import TaxonomyMatcher
    candidates = TaxonomyMatcher(frame).match_candidates("Statistics")
    assert any(item["psf_competency"] == "Computational Modeling" and
               item["matching_method"] == "competency_profile" for item in candidates)
    assert len(roles) == 1029 and roles.job_role.nunique() == 28
    assert "Critical Work" not in set(roles.job_role)
