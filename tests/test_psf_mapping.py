import pytest
import pandas as pd
from src.psf_mapping import TaxonomyMatcher, mapping_table
from src.skill_extraction import extract_skills


def test_profile_word_reuse_matches_original_scoring(taxonomy):
    import re
    from rapidfuzz import fuzz
    from src.psf_mapping import PROFILE_STOPWORDS
    from src.cleaning import normalize_text
    taxonomy.loc[0, "competency_description"] = "Statistical algorithms, communication, collaboration, modelling"
    taxonomy.loc[1, "competency_description"] = "Statistics and algorithmic communication with SQL"
    matcher = TaxonomyMatcher(taxonomy)
    for phrase in ["statistics", "statistical algorithm", "communication modelling", "collaboration statistics",
                   "irrelevant nonsense", "SQL", "data", "statistic algorithmic"]:
        terms = [t for t in re.findall(r"[\w+#.]+", normalize_text(phrase))
                 if t not in PROFILE_STOPWORDS and len(t) >= 3]
        expected = []
        if terms:
            for row, tokens in zip(matcher.rows, matcher.profile_tokens):
                scores = []
                for term in terms:
                    best = 1. if term in tokens else max((fuzz.ratio(term, token) / 100 for token in tokens
                            if len(token) >= 7), default=0.) if len(term) >= 7 else 0.
                    if best >= .85:
                        scores.append(best)
                if len(scores) / len(terms) >= .8:
                    expected.append(matcher.evidence(normalize_text(row["competency_name"]), "competency_profile", sum(scores) / len(terms)))
        assert matcher._profile_matches(phrase) == expected

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
    assert {"psf_competency_description", "psf_range_of_application"} <= set(mapping)
    assert (mapping.psf_competency == "Python").sum() == 2


def test_range_of_application_creates_partial_candidates_for_review(taxonomy):
    taxonomy.loc[3, "range_of_application"] = "SYNTHETIC tools include Oracle"
    taxonomy.loc[4, "range_of_application"] = "SYNTHETIC database systems include Oracle"
    matcher = TaxonomyMatcher(taxonomy)
    assert matcher.match("Oracle") is None  # Ambiguous evidence is never assigned arbitrarily.
    candidates = matcher.match_candidates("Oracle")
    assert len(candidates) == 2
    assert {item["matching_method"] for item in candidates} == {"range_of_application"}

    from src.alignment import calculate_alignment
    skills = pd.DataFrame({"normalized_phrase": ["oracle"], "original_phrase": ["Oracle"], "source_id": ["SYNTHETIC-1"]})
    result = calculate_alignment(skills, taxonomy)
    assert len(result) == 2
    assert set(result.status) == {"PARTIALLY ALIGNED"}
    assert set(result.match_method) == {"range_of_application"}


def test_profile_terms_create_partial_alignment_candidates(taxonomy):
    taxonomy.loc[0, "competency_description"] = "SYNTHETIC profile includes statistical algorithms and models."
    matcher = TaxonomyMatcher(taxonomy)
    candidate = matcher.match("Statistics")
    assert candidate["psf_competency"] == "Python"
    assert candidate["matching_method"] == "competency_profile"

    from src.alignment import calculate_alignment
    skills = pd.DataFrame({"normalized_phrase": ["statistics"], "original_phrase": ["Statistics"], "source_id": ["SYNTHETIC-1"]})
    result = calculate_alignment(skills, taxonomy)
    assert result.status.tolist() == ["PARTIALLY ALIGNED"]
    assert result.match_method.tolist() == ["competency_profile"]
