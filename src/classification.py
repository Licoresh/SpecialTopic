from pathlib import Path
from functools import lru_cache
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.svm import SVC
import joblib
import numpy as np
import pandas as pd
import streamlit as st
from sklearn.pipeline import Pipeline
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.naive_bayes import MultinomialNB
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold, StratifiedGroupKFold, cross_validate
from .cleaning import normalize_text
from .config import SEED
from .evaluation import evaluate_model
from .training_data import validate_labeled_data, source_disjoint_split

SELECTION_BASIS = "training_cross_validation"

MODEL_FILES = {"Multinomial Naive Bayes": "naive_bayes_pipeline.joblib", "Logistic Regression": "logistic_regression_pipeline.joblib"}
SEMANTIC_MODEL = "MiniLM + BGE-M3 INT8 ONNX (linear SVC)"
SEMANTIC_SLUG = "semantic"
SEMANTIC_ENCODERS = (
    ("sentence-transformers/all-MiniLM-L6-v2", "c21050a7ef692090620a6d037dd736908f9c7cf6"),
    ("BAAI/bge-m3", "5617a9f61b028005a4858fdac845db406aefb181"),
)


@lru_cache(maxsize=2)
def _research_encoder(model_id, revision):
    from sentence_transformers import SentenceTransformer
    from huggingface_hub import snapshot_download

    folder = snapshot_download(model_id, revision=revision, local_files_only=True)
    encoder = SentenceTransformer(folder, device="cpu", local_files_only=True)
    if model_id == "BAAI/bge-m3":
        encoder.max_seq_length = 128
    return encoder


def _encode_phrases(phrases):
    vectors = [_research_encoder(*encoder).encode(
        list(phrases), normalize_embeddings=True, batch_size=16, show_progress_bar=False)
        for encoder in SEMANTIC_ENCODERS]
    return np.column_stack(vectors) / np.sqrt(2)


class FrozenSkillEmbeddings(TransformerMixin, BaseEstimator):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return _encode_phrases(X)


def model_slug(name):
    if name == SEMANTIC_MODEL:
        return SEMANTIC_SLUG
    return "nb" if name.startswith("Multinomial") else "lr"


VECTORIZER_CONFIG = {"lowercase": True, "ngram_range": (1, 2), "sublinear_tf": True, "min_df": 1, "max_features": 10000,
                     "token_pattern": r"(?u)(?<!\w)(?:\.net|c\+\+|c#|[\w]+)(?!\w)"}

def train_model(phrases, labels, model_type="Multinomial Naive Bayes", vectorizer_config=None):
    if len(set(labels)) < 2:
        raise ValueError("Training needs at least two manually labeled categories.")
    classifier = MultinomialNB() if model_type == "Multinomial Naive Bayes" else LogisticRegression(max_iter=1000, class_weight="balanced", random_state=SEED) if model_type == "Logistic Regression" else None
    if classifier is None:
        raise ValueError("Unknown model type.")
    pipeline = Pipeline([("tfidf", TfidfVectorizer(**(VECTORIZER_CONFIG | (vectorizer_config or {})))), ("classifier", classifier)])
    pipeline.fit(list(phrases), list(labels))
    pipeline.research_model_name_ = model_type
    return pipeline

def compare_models(labeled, test_size=.2, include_irrelevant=False, vectorizer_config=None, progress=None, require_provenance=False, include_semantic=False):
    data, validation = validate_labeled_data(labeled, test_size, include_irrelevant, require_provenance)
    if validation["errors"]:
        raise ValueError(" ".join(validation["errors"]))
    train, test, split_strategy = source_disjoint_split(data, test_size, SEED)
    result = {}
    for index, name in enumerate(MODEL_FILES):
        if progress:
            progress(index / 2, f"Training and evaluating {name}")
        model = train_model(train.text, train.label, name, vectorizer_config)
        evaluation = {"metrics": {}}
        source_groups = train.source_id.fillna("").astype(str) if "source_id" in train else pd.Series(dtype=str)
        use_grouped_cv = not source_groups.empty and source_groups.str.strip().ne("").all() and source_groups.nunique() >= 2
        folds = min(5, int(train.label.value_counts().min()), int(source_groups.nunique()) if use_grouped_cv else 5)
        if folds >= 2:
            if use_grouped_cv:
                cv = StratifiedGroupKFold(folds, shuffle=True, random_state=SEED)
                cv_splits = list(cv.split(train.text, train.label, groups=source_groups))
                all_labels = set(train.label)
                complete = all(set(train.label.iloc[tr]) == all_labels and set(train.label.iloc[te]) == all_labels for tr, te in cv_splits)
                if not complete:
                    cv_splits = []
                    evaluation["cv_note"] = "Grouped cross-validation withheld because one or more source-disjoint folds omit a category."
            else:
                cv_splits = list(StratifiedKFold(folds, shuffle=True, random_state=SEED).split(train.text, train.label))
            if cv_splits:
                scores = cross_validate(model, train.text, train.label, cv=cv_splits,
                                    scoring={"macro_f1": "f1_macro", "weighted_f1": "f1_weighted", "accuracy": "accuracy"}, error_score="raise")
                for metric in ("macro_f1", "weighted_f1", "accuracy"):
                    values = scores["test_" + metric]
                    evaluation["metrics"].update({f"cv_{metric}_mean": float(np.mean(values)), f"cv_{metric}_std": float(np.std(values))})
                evaluation["metrics"]["cv_folds"] = folds
                evaluation["cv_scores"] = {metric: scores["test_"+metric].tolist() for metric in ("macro_f1", "weighted_f1", "accuracy")}
        else:
            evaluation["cv_note"] = "Cross-validation withheld: too few training examples or independent sources."
        evaluation.update(model=model, train_count=len(train), test_count=len(test), split={"strategy": split_strategy, "train_phrases": train.text.tolist(), "test_phrases": test.text.tolist(), "train_source_rows": train.source_row.tolist(), "test_source_rows": test.source_row.tolist(), "train_source_ids": sorted(train.source_id.astype(str).unique().tolist()) if "source_id" in train else [], "test_source_ids": sorted(test.source_id.astype(str).unique().tolist()) if "source_id" in test else []}, test_size=test_size, validation=validation)
        result[name] = evaluation
    if include_semantic:
        from .quantized_classifier import QuantizedSkillEmbeddings
        if not use_grouped_cv or not cv_splits:
            raise ValueError("The combined model requires valid source-grouped training folds.")
        if progress:
            progress(.65, "Encoding reviewed phrases with MiniLM and BGE-M3")
        classifier = SVC(C=10, kernel="linear", class_weight="balanced", random_state=SEED)
        pipeline = Pipeline([("embeddings", QuantizedSkillEmbeddings()), ("classifier", classifier)])
        scores = cross_validate(pipeline, train.text, train.label, cv=cv_splits,
                                scoring={"macro_f1": "f1_macro", "weighted_f1": "f1_weighted", "accuracy": "accuracy"}, error_score="raise")
        semantic_metrics = {"cv_folds": folds}
        for metric in ("macro_f1", "weighted_f1", "accuracy"):
            values = scores["test_" + metric]
            semantic_metrics.update({f"cv_{metric}_mean": float(values.mean()), f"cv_{metric}_std": float(values.std())})
        pipeline.fit(train.text, train.label)
        pipeline.research_model_name_ = SEMANTIC_MODEL
        result[SEMANTIC_MODEL] = {
            **result["Logistic Regression"], "model": pipeline, "metrics": semantic_metrics,
            "cv_scores": {key[5:]: value.tolist() for key, value in scores.items() if key.startswith("test_")},
        }

    # Require a valid training-only choice before inspecting any model's holdout.
    selected = select_best_model(result)
    for name, evaluation in result.items():
        holdout = evaluate_model(evaluation["model"], test.text, test.label)
        evaluation["metrics"].update(holdout.pop("metrics"))
        evaluation.update(holdout, selected=name == selected)
    if progress:
        progress(1., "Models evaluated")
    return result

def select_best_model(results):
    if not results:
        raise ValueError("No evaluated models are available for selection.")
    keys = ("cv_macro_f1_mean", "cv_weighted_f1_mean", "cv_macro_f1_std")
    for name, result in results.items():
        metrics = result.get("metrics", {})
        if metrics.get("cv_folds", 0) < 2 or any(
            not isinstance(metrics.get(key), (int, float, np.number)) or not np.isfinite(metrics[key])
            for key in keys
        ):
            raise ValueError(
                f"Training-only cross-validation is unavailable for {name}. "
                "Review more distinct job ads across every category, then retry training. "
                "Holdout scores cannot select a model; existing saved models are unchanged."
            )
    return max(results, key=lambda name: (
        results[name]["metrics"]["cv_macro_f1_mean"],
        results[name]["metrics"]["cv_weighted_f1_mean"],
        -results[name]["metrics"]["cv_macro_f1_std"],
    ))

def predict_category(model, phrases):
    if not len(phrases):
        return pd.DataFrame(columns=["phrase", "predicted_category", "probability"])
    if not hasattr(model, "predict_proba"):
        return pd.DataFrame({"phrase": list(phrases), "predicted_category": model.predict(phrases), "probability": None})
    probabilities = model.predict_proba(list(phrases))
    return pd.DataFrame({"phrase": list(phrases), "predicted_category": model.classes_[probabilities.argmax(axis=1)], "probability": probabilities.max(axis=1)})

def save_model(model, path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    joblib.dump(model, temporary)
    temporary.replace(path)

def load_model(path):
    # Only locally generated models are loaded by the UI; joblib is not an untrusted upload format.
    try:
        model = joblib.load(path)
        if not isinstance(model, Pipeline) or not hasattr(model, "classes_"):
            raise ValueError("Not a fitted classification pipeline.")
        return model
    except Exception as exc:
        raise ValueError("Cannot load this local model. Retrain and save a valid pipeline.") from exc

@st.cache_resource(show_spinner=False, max_entries=8)
def _cached_load_model(path, revision):
    return load_model(path)

def cached_load_model(path):
    path = Path(path)
    if not path.exists():
        raise ValueError("No trained research classifier exists. Complete manual labeling, then use Train / Retrain Models.")
    stat = path.stat()
    return _cached_load_model(str(path.resolve()), (stat.st_mtime_ns, stat.st_size))

def predict_competency_category(text, root=None):
    text = normalize_text(text)
    if not text:
        raise ValueError("Enter a nonempty competency phrase.")
    model = load_trained_model(root)
    prediction = predict_category(model, [text]).iloc[0]
    return {"predicted_label": prediction.predicted_category, "confidence_score": float(prediction.probability) if pd.notna(prediction.probability) else None,
            "model_name": getattr(model, "research_model_name_", type(model.named_steps["classifier"]).__name__)}

def load_trained_model(root=None):
    if root is None:
        from .quantized_classifier import BUNDLE, load_final_model
        if (BUNDLE / 'classifier.joblib').is_file():
            return load_final_model()
    from . import storage
    return cached_load_model(Path(root or storage.ROOT) / "models/competency_classifier.joblib")
