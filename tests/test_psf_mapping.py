import pytest
from src.psf_mapping import TaxonomyMatcher, mapping_table
from src.skill_extraction import extract_skills

def test_exact_alias_fuzzy_and_ambiguity(taxonomy):
    matcher = TaxonomyMatcher(taxonomy)
    assert matcher.match("Python")["matching_method"] == "exact"
    assert matcher.match("PYTHON")["matching_method"] == "case_insensitive"
    assert matcher.match("ML")["psf_competency"] == "machine learning"
    assert matcher.match("machine learnin")["matching_method"] == "fuzzy"
    assert matcher.match("unknown irrelevant phrase") is None
    taxonomy.loc[1, "aliases"] = "ML"
    with pytest.raises(ValueError, match="Ambiguous"):
        TaxonomyMatcher(taxonomy)

def test_mapping_evidence(jobs, taxonomy):
    extracted, _ = extract_skills(jobs, "jobs", TaxonomyMatcher(taxonomy))
    mapping = mapping_table(extracted)
    assert {"source_id", "employer_skill", "psf_competency", "confidence", "psf_job_role", "proficiency_level"} <= set(mapping)
    assert (mapping.psf_competency == "Python").sum() == 2
