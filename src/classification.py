from pathlib import Path
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

MODEL_FILES = {"Multinomial Naive Bayes": "naive_bayes_pipeline.joblib", "Logistic Regression": "logistic_regression_pipeline.joblib"}
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

def compare_models(labeled, test_size=.2, include_irrelevant=False, vectorizer_config=None, progress=None, require_provenance=False):
    data, validation = validate_labeled_data(labeled, test_size, include_irrelevant, require_provenance)
    if validation["errors"]:
        raise ValueError(" ".join(validation["errors"]))
    train, test, split_strategy = source_disjoint_split(data, test_size, SEED)
    result = {}
    for index, name in enumerate(MODEL_FILES):
        if progress:
            progress(index / 2, f"Training and evaluating {name}")
        model = train_model(train.text, train.label, name, vectorizer_config)
        evaluation = evaluate_model(model, test.text, test.label)
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
    if progress:
        progress(1., "Both models evaluated")
    return result

def select_best_model(results):
    if not results:
        raise ValueError("No evaluated models are available for selection.")
    return max(results, key=lambda name: (results[name]["metrics"]["macro_f1"], results[name]["metrics"]["weighted_f1"],
                                         float(results[name]["per_class"]["f1-score"].min()), -results[name]["metrics"].get("cv_macro_f1_std", 0.)))

def predict_category(model, phrases):
    if not len(phrases):
        return pd.DataFrame(columns=["phrase", "predicted_category", "probability"])
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
    return {"predicted_label": prediction.predicted_category, "confidence_score": float(prediction.probability),
            "model_name": getattr(model, "research_model_name_", type(model.named_steps["classifier"]).__name__)}

def load_trained_model(root=None):
    from . import storage
    return cached_load_model(Path(root or storage.ROOT) / "models/competency_classifier.joblib")
