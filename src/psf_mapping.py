from functools import lru_cache
from pathlib import Path
import re
import numpy as np
import pandas as pd
from rapidfuzz import fuzz, process
from .cleaning import normalize_text
from .validation import validate_taxonomy

PROFILE_STOPWORDS = {"a", "an", "and", "application", "applications", "appropriate", "based", "by", "data",
                     "for", "from", "good", "include", "including", "in", "into", "of", "on", "or",
                     "related", "skill", "skills", "system", "systems", "technology", "technologies",
                     "the", "their", "this", "to", "use", "using", "various", "with", "work"}

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
        self.profiles = [normalize_text(row.get("competency_description", "")) for row in self.rows]
        self.profile_tokens = [set(re.findall(r"[\w+#.]+", text)) for text in self.profiles]
        self.profile_cache = {}
        self.ranges = [normalize_text(row.get("range_of_application", "")) for row in self.rows]
        self.range_cache = {}
        self.pattern = re.compile(r"(?<![\w+#])(?:" + "|".join(re.escape(k) for k in sorted(self.terms, key=len, reverse=True)) + r")(?![\w+#])", re.I)
        self.fuzzy_threshold = fuzzy_threshold
        self.semantic_threshold = semantic_threshold
        self.encoder = semantic_model(semantic_path) if semantic_path else None
        self.vectors = self.encoder.encode([
            ". ".join(str(r.get(field, "")).strip() for field in
                       ("competency_name", "competency_description", "range_of_application") if str(r.get(field, "")).strip())
            for r in self.rows
        ], normalize_embeddings=True) if self.encoder else None
        self.cache = {}

    def evidence(self, key, method, score):
        row = self.rows[self.terms[key][0]]
        return {"psf_competency": row["competency_name"], "competency_id": row["competency_id"],
                "psf_category": row.get("competency_category", ""), "job_role": row.get("job_role", ""),
                "proficiency_level": row.get("proficiency_level", ""), "matching_method": method,
                "similarity_score": float(score), "confidence": float(score),
                "psf_competency_description": row.get("competency_description", ""),
                "psf_range_of_application": row.get("range_of_application", ""),
                "source_page": row.get("source_page", ""), "source_url": row.get("source_url", ""), "source_hash": row.get("source_hash", "")}

    def exact_in_text(self, text):
        for match in self.pattern.finditer(text):
            key = normalize_text(match.group())
            method = self.terms[key][1]
            if method == "exact" and match.group() != self.originals[key]:
                method = "case_insensitive"
            yield match.group(), match.start(), match.end(), self.evidence(key, method, 1.)

    def _standard_match(self, phrase, normalized=None):
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

    def _range_matches(self, phrase, normalized=None):
        key = normalize_text(normalized or phrase)
        if key in self.range_cache:
            return self.range_cache[key]
        if len(key) < 2:
            return []
        pattern = re.compile(r"(?<!\w)" + re.escape(key) + r"(?!\w)", re.I)
        matches = [self.evidence(normalize_text(row["competency_name"]), "range_of_application", 1.)
                   for row, text in zip(self.rows, self.ranges) if pattern.search(text)]
        self.range_cache[key] = matches
        return matches

    def _profile_matches(self, phrase, normalized=None):
        key = normalize_text(normalized or phrase)
        if key in self.profile_cache:
            return self.profile_cache[key]
        if len(key) < 3:
            return []
        terms = [term for term in re.findall(r"[\w+#.]+", key)
                 if term not in PROFILE_STOPWORDS and len(term) >= 3]
        if not terms:
            return []
        matches = []
        for row, tokens in zip(self.rows, self.profile_tokens):
            token_scores = []
            for term in terms:
                if term in tokens:
                    token_scores.append(1.)
                elif len(term) >= 7:
                    best = max((fuzz.ratio(term, token) / 100 for token in tokens if len(token) >= 7), default=0.)
                    if best >= .85:
                        token_scores.append(best)
            if len(token_scores) / len(terms) >= .8:
                score = sum(token_scores) / len(terms)
                evidence = self.evidence(normalize_text(row["competency_name"]), "competency_profile", score)
                matches.append(evidence)
        self.profile_cache[key] = matches
        return matches

    def match_candidates(self, phrase, normalized=None):
        standard = self._standard_match(phrase, normalized)
        if standard and standard["matching_method"] in {"exact", "alias", "case_insensitive", "lemma_phrase"}:
            return [standard]
        ranges = self._range_matches(phrase, normalized)
        profiles = self._profile_matches(phrase, normalized)
        if ranges or profiles:
            # Prefer explicit Range evidence when both it and profile prose match
            # the same competency; retain every distinct competency candidate.
            candidates = {}
            for match in ranges + profiles:
                candidates.setdefault(match["competency_id"], match)
            return list(candidates.values())
        return [standard] if standard else []

    def match(self, phrase, normalized=None):
        candidates = self.match_candidates(phrase, normalized)
        return candidates[0] if len(candidates) == 1 else None

def mapping_table(extracted):
    if extracted.empty:
        return pd.DataFrame()
    cols = ["extraction_id", "source_id", "source_type", "original_phrase", "normalized_phrase", "psf_competency", "competency_id", "psf_category", "job_role", "proficiency_level", "psf_competency_description", "psf_range_of_application", "matching_method", "similarity_score", "confidence", "source_page", "source_url", "source_hash", "ml_category", "ml_confidence"]
    return extracted.reindex(columns=cols).rename(columns={"original_phrase": "employer_skill", "normalized_phrase": "normalized_skill", "job_role": "psf_job_role", "matching_method": "match_method"})
