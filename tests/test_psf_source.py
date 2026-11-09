"""SYNTHETIC DATA — NOT RESEARCH DATA; framework rows use fictional sources."""
import hashlib
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
    assert roles.job_role.nunique() == 31
    assert "Critical Work" not in set(roles.job_role)
    evidence = set(roles[["competency_name", "job_role", "proficiency_level", "source_page"]].itertuples(index=False, name=None))
    assert ("Collaboration", "Data Governance Officer", "Advanced", 55) in evidence
    assert ("Process Improvement and Optimization", "Business Analytics Manager", "Level 4", 44) in evidence
    assert ("Product Management", "Chief AI Engineer", "Level 5", 89) in evidence
    assert ("Product Management", "Chief Technology Officer", "Level 6", 91) in evidence
    assert ("Research", "Machine Learning Engineer", "Level 3", 72) in evidence
    assert ("Self Management", "Research Manager", "Basic", 97) in evidence
    assert ("Computational Modeling", "Machine Learning Engineer", "Level 3", 72) in evidence
    assert not roles.loc[roles.competency_name.eq("Performance Management"), "job_role"].eq("Research Manager").any()
    assert roles.loc[roles.job_role.eq("AI Engineer"), "occupational_family"].eq("AI Engineering").all()
    assert roles.loc[roles.job_role.eq("Data Scientist"), "occupational_family"].eq("Data Science").all()
    from src.psf_source import OCCUPATIONAL_FAMILIES, reference_role_profiles
    assert set(frame.set_index("competency_name").loc["Adaptability", "occupational_family"].split("; ")) == set(OCCUPATIONAL_FAMILIES)
    profiles = reference_role_profiles(ROOT, frame)
    assert len(profiles) == 31
    manager = next(row for row in profiles if row["job_role"] == "Research Manager")
    assert "actionable business insights" in manager["role_description"]
    assert manager["role_source_page"] == 96 and manager["source_page"] == 97
    assert all(len(row["role_description"]) > 100 for row in profiles)

    # Independently audit each table line, including known spelling variants.
    import re
    from pypdf import PdfReader
    reader = PdfReader(path)
    names = {name.casefold(): name for name in frame.competency_name}
    for page in roles.source_page.unique():
        actual = set(roles.loc[roles.source_page.eq(page), ["competency_name", "proficiency_level"]].itertuples(index=False, name=None))
        for line in reader.pages[int(page) - 1].extract_text().splitlines():
            for hit in re.finditer(r"(.+?)\s+(Level [1-6]|Basic|Intermediate|Advanced)\b", line):
                name = re.sub(r"^Level [1-6]\s+", "", hit[1].strip()).casefold()
                name = name.replace("self-management", "self management").replace("modelling", "modeling")
                assert name in names, (page, name)
                assert (names[name], hit[2]) in actual, (page, name, hit[2])


def test_bundled_default_reference_matches_the_included_official_pdf():
    from src.config import ROOT
    reference = pd.read_csv(ROOT / "data/reference/psf_aai_default.csv", dtype=str, keep_default_na=False)
    source_hash = hashlib.sha256((ROOT / "data/reference/psf_aai_official.pdf").read_bytes()).hexdigest()

    assert len(reference) == reference.competency_name.nunique() == 94
    assert reference.source_hash.eq(source_hash).all()
    assert reference.review_status.eq("Researcher verified").all()
    assert reference.range_of_application.str.contains("SQL", case=False).any()
    by_name = reference.set_index("competency_name")
    assert "Data Governance Officer" in by_name.loc["Collaboration", "job_role"].split("; ")
    assert "Machine Learning Engineer" in by_name.loc["Research", "job_role"].split("; ")
    assert by_name.loc["Collaboration", "aliases"] == "collaborate"
    assert by_name.loc["Research", "aliases"] == "conduct research"
    parsed, _ = parse_framework(ROOT / "data/reference/psf_aai_official.pdf")
    pd.testing.assert_series_equal(by_name.job_role.sort_index(), parsed.set_index("competency_name").job_role.sort_index())


def test_research_reference_gets_released_links_for_the_same_source(workspace):
    from src import storage
    from src.config import ROOT

    path = workspace / "data/reference/psf_aai_default.csv"
    path.parent.mkdir(parents=True)
    path.write_bytes((ROOT / "data/reference/psf_aai_default.csv").read_bytes())
    reference = pd.read_csv(path, dtype=str, keep_default_na=False).set_index("competency_name", drop=False)
    saved = reference.loc[["Collaboration", "Research", "Performance Management"]].reset_index(drop=True)
    saved.loc[0, "job_role"] = "Researcher custom role"
    saved.loc[0, "aliases"] = ""
    saved.loc[1, "source_hash"] = "other-source"
    saved.loc[1, "aliases"] = "custom wording"
    saved.loc[2, "job_role"] = "Research Manager; Researcher custom role"
    storage.save_frame("cleaned_psf_aai", saved)
    for effective in (storage.read_frame("cleaned_psf_aai"), training_taxonomy(workspace)):
        assert effective.loc[0, "aliases"] == "collaborate"
        assert {"Researcher custom role", "Data Governance Officer"} <= set(effective.loc[0, "job_role"].split("; "))
        assert effective.loc[1, "aliases"] == "custom wording"
        assert "Research Manager" not in effective.loc[2, "job_role"].split("; ")
        assert "Researcher custom role" in effective.loc[2, "job_role"].split("; ")
    original = pd.read_csv(workspace / "data/processed/cleaned_psf_aai.csv", dtype=str, keep_default_na=False)
    assert original.loc[0, "aliases"] == ""
