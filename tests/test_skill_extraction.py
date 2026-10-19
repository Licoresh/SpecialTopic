import pandas as pd
from src.skill_extraction import extract_skills
from src.psf_mapping import TaxonomyMatcher
from src.analytics import accepted_skills

def test_extraction_deduplicates_and_traces(jobs, taxonomy):
    jobs.loc[0, "cleaned_text"] += " Python Python programming PYTHON"
    output, diagnostics = extract_skills(jobs, "jobs", TaxonomyMatcher(taxonomy))
    # Preserve distinct employer terms that map to one reference competency;
    # repeated mentions of the same normalized employer phrase count once.
    assert not output.duplicated(["source_id", "normalized_phrase"]).any()
    assert len(diagnostics) == len(jobs)
    assert "C++".casefold() in set(accepted_skills(output).matched_competency)
    assert output.loc[output.psf_competency.eq("Python"), "original_text"].str.len().min() > 0

def test_annotation_rejection(jobs):
    labels = pd.DataFrame([{"normalized_phrase":"python", "label":"IRRELEVANT", "psf_competency":""}])
    output, _ = extract_skills(jobs, "jobs", annotations=labels)
    assert "python" not in set(accepted_skills(output).matched_competency)


def test_reviewed_psf_assignment_does_not_spread_between_ads(jobs, taxonomy):
    labels = pd.DataFrame([{"normalized_phrase":"python", "label":"Technical / Digital",
                            "psf_competency":"SQL", "source_id":jobs.source_id.iloc[0]}])
    output, _ = extract_skills(jobs, "jobs", TaxonomyMatcher(taxonomy), annotations=labels)
    python = output[output.normalized_phrase.eq("python")].set_index("source_id")
    assert python.loc[jobs.source_id.iloc[0], "psf_competency"] == "SQL"
    assert python.loc[jobs.source_id.iloc[1], "psf_competency"] == "Python"
    assert python.loc[jobs.source_id.iloc[1], "matching_method"] != "human_annotation"

def test_surface_phrase_annotation_survives_lemmatization(jobs):
    jobs.loc[0, "cleaned_text"] = "Models transform databases."
    labels = pd.DataFrame([{"normalized_phrase":"models", "label":"Research Category", "psf_competency":""}])
    output, _ = extract_skills(jobs, "jobs", annotations=labels)
    row = output[output.original_phrase.eq("Models")].iloc[0]
    assert row.competency_category == "Research Category" and row.accepted

def test_human_label_preserved_and_model_shown_separately(jobs, labeled):
    from src.classification import train_model
    model = train_model(labeled.phrase, labeled.label)
    human = pd.DataFrame([{"phrase":"Python", "normalized_phrase":"python", "label":"Human Reviewed Category", "psf_competency":""}])
    output, _ = extract_skills(jobs, "jobs", model=model, annotations=human)
    row = output[output.original_phrase.eq("Python")].iloc[0]
    assert row.competency_category == row.human_label == "Human Reviewed Category"
    assert row.model_prediction in model.classes_
    assert row.agreement == "Mismatch" and 0 <= row.ml_confidence <= 1
    assert output.loc[output.human_label.eq(""), "agreement"].eq("Not Reviewed").all()

def test_positive_only_classifier_does_not_establish_relevance(jobs, labeled):
    from src.classification import train_model
    model = train_model(labeled.phrase, labeled.label)
    jobs.loc[0, "cleaned_text"] = "Lunch cafeteria."
    output, _ = extract_skills(jobs.iloc[:1], "jobs", model=model)
    assert output.model_prediction.ne("").all()
    assert not output.accepted.any()
