"""Explicit train/evaluate/publish action, shared by the UI and integration tests."""
import importlib.metadata
import json
import platform
from pathlib import Path
import pandas as pd
from . import storage
from .classification import compare_models, select_best_model, save_model, MODEL_FILES, VECTORIZER_CONFIG
from .training_data import load_labeled_data, labeled_file_hash
from .reporting import export_csv
from .utils import timestamp, frame_hash
from .training_sources import resolve_training_file
from .training_lock import exclusive_training, ensure_training_lease
from . import supabase_store

def read_model_metadata(root=None):
    if supabase_store.configured():
        return storage.read_json("model_metadata", {})
    path = Path(root or storage.ROOT) / "models/model_metadata.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

def training_data_changed(root=None):
    root = Path(root or storage.ROOT)
    meta = read_model_metadata(root)
    if not meta:
        return False
    if supabase_store.configured():
        return meta.get("shared_annotation_hash") != frame_hash(storage.read_frame("labeled_competencies"))
    path = resolve_training_file(root)
    return str(path.resolve()) != meta.get("training_file") or meta.get("training_file_hash", meta.get("training_data_hash")) != labeled_file_hash(path)

@exclusive_training
def train_and_save_models(test_size=.2, include_irrelevant=False, vectorizer_config=None, progress=None):
    root = storage.ROOT
    shared = supabase_store.configured()
    if shared:
        supabase_store.clear_read_cache()
        labels = storage.read_frame("labeled_competencies").copy(deep=True)
        shared_hash = frame_hash(labels)
        # Immutable input snapshot; labeling can continue during this run.
        path = root / "models/snapshots" / f"{shared_hash}.csv"
        storage.atomic_bytes(path, export_csv(labels))
    else:
        path = resolve_training_file(root)
        labels = load_labeled_data(path)
    before_hash = labeled_file_hash(path)
    results = compare_models(labels, test_size, include_irrelevant, vectorizer_config, progress, require_provenance=True)
    if labeled_file_hash(path) != before_hash:
        raise ValueError("Annotations changed during training. No model was published; retry with the current dataset.")
    ensure_training_lease()
    selected = select_best_model(results)
    trained_at = timestamp()
    vectorizer = VECTORIZER_CONFIG | (vectorizer_config or {})
    comparison, reports, matrices, predictions, details = [], [], [], [], {}
    for name, result in results.items():
        slug = "nb" if name.startswith("Multinomial") else "lr"
        comparison.append({"model": name, **result["metrics"], "selected": name == selected})
        per_class = result["per_class"].reset_index(names="class")
        confusion = result["confusion"].rename_axis("actual").reset_index()
        reports.append(per_class.assign(model=name))
        matrices.append(confusion.melt(id_vars="actual", var_name="predicted", value_name="count").assign(model=name))
        predictions.append(result["predictions"][["phrase", "true_label", "predicted_label", "confidence", "correct"]].assign(model=name))
        details[name] = {"metrics": result["metrics"], "train_count": result["train_count"], "test_count": result["test_count"],
                         "split": result["split"], "cv_note": result.get("cv_note", ""), "cv_scores": result.get("cv_scores", {}),
                         "test_fraction": test_size, "random_state": 42, "training_hash": frame_hash(labels),
                         "training_data_hash": before_hash, "timestamp": trained_at, "features": vectorizer,
                         "config": result["model"].named_steps["classifier"].get_params()}
    winner = results[selected]
    validation = winner["validation"]
    metadata = {"training_timestamp": trained_at, "training_data_hash": before_hash, "dataset_rows_used": validation["rows_used"],
                "training_file": str(path.resolve()), "training_file_hash": before_hash, "rows_available": len(labels), "rows_used": validation["rows_used"],
                "number_of_classes": validation["number_of_classes"], "class_names": list(winner["model"].classes_),
                "class_distribution": validation["class_distribution"], "train_size": winner["train_count"], "test_size": winner["test_count"],
                "test_fraction": test_size, "model_name": selected, "vectorizer_config": vectorizer, "random_state": 42,
                "selected_model": selected, "tfidf_config": vectorizer, "python_version": platform.python_version(), "scikit_learn_version": importlib.metadata.version("scikit-learn"),
                **winner["metrics"], "cross_validation_results": {name: {"fold_scores": r.get("cv_scores", {}), "summary": {k:v for k,v in r["metrics"].items() if k.startswith("cv_")}, "note": r.get("cv_note", "")} for name,r in results.items()},
                "software_versions": {"python": platform.python_version(), **{name: importlib.metadata.version(name) for name in ("scikit-learn", "pandas", "numpy", "joblib", "streamlit")}},
                "selection_rule": "Highest holdout Macro F1, then Weighted F1, then minimum per-class F1, then lower CV Macro F1 standard deviation; original model order breaks exact ties.",
                "include_irrelevant": include_irrelevant, "validation": validation, "split": winner["split"],
                "interpretation": "Based on the current labeled validation sample. Minimum sample gates do not establish research accuracy; independent validation is still required.",
                "classifier_config": details[selected]["config"], "refit_on_holdout": False}
    from .background_tasks import begin_publication
    begin_publication()
    # No artifacts are written before both models, their evaluation, and selection succeed.
    if shared:
        metadata["shared_annotation_hash"] = shared_hash
        metadata["shared_run_id"] = supabase_store.session_state()["training_run_id"]
        metadata["snapshot_note"] = "Evaluated on a fixed Supabase reviewed-label snapshot; subsequent team edits are not included."
    for name, result in results.items():
        slug = "nb" if name.startswith("Multinomial") else "lr"
        save_model(result["model"], root / "models" / MODEL_FILES[name])
        storage.save_frame(f"evaluation_{slug}_per_class", result["per_class"].reset_index(names="class"))
        storage.save_frame(f"evaluation_{slug}_confusion", result["confusion"].reset_index(names="actual"))
        storage.save_frame(f"evaluation_{slug}_predictions", result["predictions"])
    table = pd.DataFrame(comparison)
    storage.save_frame("model_metrics", table)
    storage.save_json("training_details", details)
    for name, frame in {"model_metrics": table, "model_comparison": table, "classification_report": pd.concat(reports, ignore_index=True), "confusion_matrix": pd.concat(matrices, ignore_index=True), "test_predictions": pd.concat(predictions, ignore_index=True)}.items():
        storage.atomic_bytes(root / "outputs/tables" / f"{name}.csv", export_csv(frame))
    save_model(winner["model"], root / "models/competency_classifier.joblib")
    storage.atomic_bytes(root / "models/model_metadata.json", json.dumps(metadata, indent=2, default=str).encode("utf-8"))
    storage.save_json("selected_model", {"name": selected, **details[selected]})
    if shared:
        storage.save_frame("training_snapshot", labels)
        storage.save_json("model_metadata", metadata)
    return metadata, table
