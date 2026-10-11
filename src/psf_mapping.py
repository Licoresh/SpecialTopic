from functools import lru_cache
from pathlib import Path
import re
import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process
from .cleaning import normalize_text
from .validation import validate_taxonomy

@lru_cache(maxsize=2)
def semantic_model(path):
    if not Path(path).is_dir():
        raise ValueError("Semantic model must be an existing local sentence-transformers directory.")
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise ValueError("Install sentence-transformers to enable local semantic matching.") from exc
    return SentenceTransformer(path, local_files_only=True)

class TaxonomyMatcher:
    def __init__(self, taxonomy, fuzzy_threshold=.9, semantic_path="", semantic_threshold=.8):
        validate_taxonomy(taxonomy)
        self.rows = taxonomy.fillna("").to_dict("records")
        self.terms = {}
        self.originals = {}
        for i, row in enumerate(self.rows):
            terms = [(row["competency_name"], "exact")]
            for key in ("aliases", "keywords"):
                terms.extend((v.strip(), "alias") for v in str(row.get(key, "")).split(";") if v.strip())
            for term, method in terms:
                key = normalize_text(term)
                if key in self.terms and self.terms[key][0] != i:
                    raise ValueError(f"Ambiguous taxonomy alias '{term}': assign it to one competency.")
                self.terms[key] = (i, method)
                self.originals[key] = term
        self.pattern = re.compile(r"(?<![\w+#])(?:" + "|".join(re.escape(k) for k in sorted(self.terms, key=len, reverse=True)) + r")(?![\w+#])", re.I)
        self.fuzzy_threshold = fuzzy_threshold
        self.semantic_threshold = semantic_threshold
        self.encoder = semantic_model(semantic_path) if semantic_path else None
        self.vectors = self.encoder.encode([r["competency_name"] + ". " + r.get("competency_description", "") for r in self.rows], normalize_embeddings=True) if self.encoder else None
        self.cache = {}

    def evidence(self, key, method, score):
        row = self.rows[self.terms[key][0]]
        return {"psf_competency": row["competency_name"], "competency_id": row["competency_id"],
                "psf_category": row.get("competency_category", ""), "job_role": row.get("job_role", ""),
                "proficiency_level": row.get("proficiency_level", ""), "matching_method": method,
                "similarity_score": float(score), "confidence": float(score),
                "source_page": row.get("source_page", ""), "source_url": row.get("source_url", ""), "source_hash": row.get("source_hash", "")}

    def exact_in_text(self, text):
        for match in self.pattern.finditer(text):
            key = normalize_text(match.group())
            method = self.terms[key][1]
            if method == "exact" and match.group() != self.originals[key]:
                method = "case_insensitive"
            yield match.group(), match.start(), match.end(), self.evidence(key, method, 1.)

    def match(self, phrase, normalized=None):
        cache_key = (phrase, normalized)
        if cache_key in self.cache:
            return self.cache[cache_key]
        key = normalize_text(phrase)
        result = None
        if key in self.terms:
            method = self.terms[key][1]
            if method == "exact" and phrase != self.originals[key]:
                method = "case_insensitive"
            result = self.evidence(key, method, 1.)
        elif normalized and normalize_text(normalized) in self.terms:
            result = self.evidence(normalize_text(normalized), "lemma_phrase", 1.)
        elif len(key) >= 5:
            best = process.extractOne(key, self.terms.keys(), scorer=fuzz.ratio, score_cutoff=self.fuzzy_threshold * 100)
            if best:
                result = self.evidence(best[0], "fuzzy", best[1]/100)
        if result is None and self.encoder and len(key) >= 4:
            vector = self.encoder.encode([phrase], normalize_embeddings=True)[0]
            scores = self.vectors @ vector
            i = int(np.argmax(scores))
            if scores[i] >= self.semantic_threshold:
                result = self.evidence(normalize_text(self.rows[i]["competency_name"]), "semantic", scores[i])
        self.cache[cache_key] = result
        return result

def mapping_table(extracted):
    if extracted.empty:
        return pd.DataFrame()
    cols = ["extraction_id", "source_id", "source_type", "original_phrase", "normalized_phrase", "psf_competency", "competency_id", "psf_category", "job_role", "proficiency_level", "matching_method", "similarity_score", "confidence", "source_page", "source_url", "source_hash", "ml_category", "ml_confidence"]
    return extracted.reindex(columns=cols).rename(columns={"original_phrase": "employer_skill", "normalized_phrase": "normalized_skill", "job_role": "psf_job_role", "matching_method": "match_method"})
