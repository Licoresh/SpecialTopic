import re
import pandas as pd
from .cleaning import clean_text, normalize_text
from .preprocessing import extract_candidate_phrases
from .utils import digest

# General discovery vocabulary only; these are NOT asserted PSF-AAI competencies.
VOCABULARY = {
    "Technical / Digital": "Python;R;SQL;C++;C#;.NET;Java;JavaScript;Power BI;Tableau;Excel;Git;Docker;Kubernetes;cloud computing;cybersecurity;software engineering",
    "AI / Machine Learning": "machine learning;artificial intelligence;deep learning;natural language processing;computer vision;generative AI;large language models;MLOps;model evaluation;neural networks",
    "Data / Analytics": "data analysis;data analytics;data engineering;data visualization;statistics;statistical analysis;data mining;business intelligence;data governance;data privacy",
    "Soft / Enabling": "critical thinking;problem solving;communication skills;teamwork;collaboration;adaptability;creativity",
    "Leadership / Management": "leadership;project management;people management",
    "Education / Qualification": "bachelor;master;doctorate;PhD;certification",
}
GENERAL = {normalize_text(term): cat for cat, terms in VOCABULARY.items() for term in terms.split(";")}
GENERAL_PATTERN = re.compile(r"(?<![\w+#])(?:" + "|".join(re.escape(k) for k in sorted(GENERAL, key=len, reverse=True)) + r")(?![\w+#])", re.I)
EXTRACTION_COLUMNS = "extraction_id source_type source_id original_text original_phrase normalized_phrase matched_competency competency_category matching_method similarity_score confidence_score psf_competency competency_id psf_category job_role proficiency_level psf_competency_description psf_range_of_application confidence ml_category ml_confidence human_label model_prediction model_name agreement skill_type accepted start_char end_char source_page source_url source_hash".split()

def extract_skills(frame, source_type, matcher=None, model=None, annotations=None, **options):
    if frame.empty:
        return pd.DataFrame(columns=EXTRACTION_COLUMNS), pd.DataFrame()
    from .background_tasks import checkpoint
    progress = options.pop("progress", None) or (lambda value, message: None)
    progress(.05, "Preparing NLP phrases from the complete source text")
    texts = frame.cleaned_text.map(clean_text)
    options.setdefault("priority_phrases", GENERAL.keys())
    processed = extract_candidate_phrases(texts, progress=progress, **options)
    annotation_map = {}
    psf_annotations = {}
    if annotations is not None and not annotations.empty:
        for row in annotations.fillna("").to_dict("records"):
            if str(row.get("label", "")).strip():
                row["label"] = str(row["label"]).strip()
                if row["label"].casefold() == "irrelevant":
                    row["label"] = "IRRELEVANT"
                original = row.get("phrase") or row.get("normalized_phrase", "")
                annotation_map[normalize_text(original)] = row
                annotation_map[normalize_text(row.get("normalized_phrase") or original)] = row
                # Category training is phrase-based; reviewed PSF meaning is source-specific.
                if row.get("psf_competency"):
                    for source_id in str(row.get("source_id", "")).split(";"):
                        if source_id.strip():
                            for term in (original, row.get("normalized_phrase") or original):
                                psf_annotations[(normalize_text(term), source_id.strip())] = row["psf_competency"]
    extracted, diagnostics = [], []
    # NLP and model predictions are reused for repeated text/phrases.
    evidence_by_text = {}
    progress(.25, "Scanning full text against vocabulary and PSF-AAI")
    for number, text in enumerate(processed):
        checkpoint()
        progress(.25 + .1 * number / max(len(processed), 1), f"Scanning text {number + 1:,} of {len(processed):,}")
        evidence = []
        if matcher:
            evidence.extend((p, normalize_text(p), a, b, m) for p, a, b, m in matcher.exact_in_text(text))
        for hit in GENERAL_PATTERN.finditer(text):
            evidence.append((hit.group(), normalize_text(hit.group()), hit.start(), hit.end(), None))
        evidence.extend((*p, None) for p in processed[text]["phrases"])
        evidence_by_text[text] = evidence
    progress(.35, "Classifying candidate phrases")
    predictions = {}
    if model is not None:
        phrases = list(dict.fromkeys(normalize_text(p[1] or p[0]) for evidence in evidence_by_text.values() for p in evidence))
        if phrases:
            probabilities = model.predict_proba(phrases)
            predictions = {p: (str(model.classes_[probs.argmax()]), float(probs.max())) for p, probs in zip(phrases, probabilities)}
    for number, ((_, row), text) in enumerate(zip(frame.iterrows(), texts)):
        checkpoint()
        progress(.4 + .5 * number / len(frame), f"Mapping advertisement {number + 1:,} of {len(frame):,}")
        evidence = evidence_by_text[text]
        seen = set()
        for phrase, normal, start, end, mapped in evidence:
            normal = normalize_text(normal)
            mapped = mapped or (matcher.match(phrase, normal) if matcher else None)
            annotation = annotation_map.get(normalize_text(phrase), annotation_map.get(normal))
            category = GENERAL.get(normal, "UNCLASSIFIED")
            ml_cat, ml_score = predictions.get(normal, ("", None))
            score = ml_score if ml_score is not None else 0.
            can_screen_relevance = model is not None and "IRRELEVANT" in model.classes_
            accepted = mapped is not None or normal in GENERAL or (can_screen_relevance and ml_cat not in ("", "IRRELEVANT") and score >= .6)
            if mapped:
                category = mapped["psf_category"] or category
            elif score >= .6:
                category = ml_cat
            if annotation:
                category = annotation["label"]
                accepted = category != "IRRELEVANT"
                assignment = psf_annotations.get((normalize_text(phrase), str(row.source_id)),
                                                 psf_annotations.get((normal, str(row.source_id))))
                if assignment and matcher:
                    mapped = matcher.match(assignment)
                    if mapped:
                        mapped = mapped | {"matching_method": "human_annotation", "confidence": 1.}
            skill = mapped["psf_competency"] if mapped else normal
            if normal in seen:
                continue
            seen.add(normal)
            result = {"extraction_id": digest([row.source_id, normal])[:24], "source_type": source_type,
                      "source_id": row.source_id, "original_text": row.original_text, "original_phrase": phrase,
                      "normalized_phrase": normal, "matched_competency": skill, "competency_category": category,
                      "matching_method": "human_annotation" if annotation else "general_vocabulary" if normal in GENERAL else "ml_candidate" if accepted else "candidate",
                      "similarity_score": 0., "confidence": score if accepted else 0., "psf_competency": "", "competency_id": "", "psf_category": "", "job_role": "", "proficiency_level": "",
                      "ml_category": ml_cat, "ml_confidence": ml_score, "human_label": annotation["label"] if annotation else "", "model_prediction": ml_cat,
                      "model_name": getattr(model, "research_model_name_", type(model.named_steps["classifier"]).__name__) if model is not None else "",
                      "agreement": ("Match" if annotation["label"] == ml_cat else "Mismatch") if annotation and ml_cat else "Not Reviewed" if not annotation else "",
                      "accepted": accepted, "start_char": start, "end_char": end}
            if mapped:
                result.update(mapped)
            result["confidence_score"] = result["confidence"]
            result["skill_type"] = "Soft / Enabling" if any(k in category.casefold() for k in ("soft", "enabling", "leadership")) else "Technical" if any(k in category.casefold() for k in ("technical", "digital", "data", "analytics", "machine", "ai /")) else "Other / Unclassified"
            extracted.append(result)
        diagnostics.append({"source_id": row.source_id, "candidate_limit_reached": processed[text]["truncated"], "lemmas": processed[text]["lemmas"], "nlp_text": text})
    return pd.DataFrame(extracted, columns=EXTRACTION_COLUMNS).fillna({"source_page": "", "source_url": "", "source_hash": ""}), pd.DataFrame(diagnostics)
