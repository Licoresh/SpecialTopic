"""Export the evaluated classifier for browser inference and publish it by explicit approval."""

from datetime import datetime
from functools import lru_cache
from io import BytesIO
import json
import math
import re

import requests

from . import storage, supabase_store
from .classification import SELECTION_BASIS, VECTORIZER_CONFIG, load_model
from .config import LABELS
from .model_training import read_model_metadata, training_data_changed
from .utils import digest


TOKEN_SETTING = "PUBLIC_MODEL_GITHUB_TOKEN"
MODEL_PATH = "public-web/site/model.json"
REPOSITORY = "Licoresh/SpecialTopic"
BRANCH = "main"
CONFIG_PATH = "src/config.py"
MAX_ARTIFACT_BYTES = 24_000_000


def publication_configured():
    return bool(supabase_store._setting(TOKEN_SETTING))


def _require_admin():
    if not supabase_store.is_admin():
        raise ValueError("Only a workspace administrator can prepare or publish a public classifier.")


@lru_cache(maxsize=1)
def _casefold_overrides():
    return {char: char.casefold() for char in map(chr, range(0x110000)) if char.casefold() != char.lower()}


def _browser_artifact(model, metadata):
    vectorizer = model.named_steps["tfidf"]
    classifier = model.named_steps["classifier"]
    settings = vectorizer.get_params()
    supported = {"analyzer": "word", "strip_accents": None, "preprocessor": None,
                 "tokenizer": None, "stop_words": None, "norm": "l2", "binary": False, "use_idf": True,
                 **{name: VECTORIZER_CONFIG[name] for name in ("token_pattern", "lowercase", "sublinear_tf", "ngram_range")}}
    if any(settings[name] != value for name, value in supported.items()):
        raise ValueError("This classifier uses a text configuration that the public site cannot load.")

    classes = [str(value) for value in model.classes_]
    name = metadata["model_name"]
    if (classes != metadata.get("class_names") or len(classes) < 2 or not set(classes) <= set(LABELS)
            or name != getattr(model, "research_model_name_", None)):
        raise ValueError("The selected model does not match the evaluated study categories.")
    if name == "Logistic Regression" and type(classifier).__name__ == "LogisticRegression":
        weights, intercepts = classifier.coef_, classifier.intercept_
        kind = "logistic"
    elif name == "Multinomial Naive Bayes" and type(classifier).__name__ == "MultinomialNB":
        weights, intercepts = classifier.feature_log_prob_, classifier.class_log_prior_
        kind = "multinomial_nb"
    else:
        raise ValueError("The selected classifier cannot run in the public browser.")

    model_data = {"schema": 1, "name": name, "trainedAt": metadata["training_timestamp"],
                  "kind": kind, "classes": classes, "terms": vectorizer.get_feature_names_out().tolist(),
                  "idf": vectorizer.idf_.tolist(), "weights": weights.tolist(), "intercepts": intercepts.tolist(),
                  "casefold": _casefold_overrides()}
    signature = json.dumps(model_data, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    model_data["version"] = digest(signature)[:16]
    content = json.dumps(model_data, ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode()
    if len(content) > MAX_ARTIFACT_BYTES:
        raise ValueError("The classifier is too large for browser release. Train again with fewer TF-IDF features.")
    return model_data["version"], content


def prepare_release():
    if supabase_store.configured():
        supabase_store.clear_read_cache()
    _require_admin()
    metadata = read_model_metadata()
    split = metadata.get("split", {})
    train_ids = set(split.get("train_source_ids", []))
    test_ids = set(split.get("test_source_ids", []))
    metrics = [metadata.get(key) for key in ("accuracy", "macro_f1", "weighted_f1", "cv_macro_f1_mean")]
    if (metadata.get("selection_basis") != SELECTION_BASIS or metadata.get("validation", {}).get("valid") is not True
            or not split.get("strategy", "").startswith("source-disjoint") or len(train_ids) < 2 or len(test_ids) < 2
            or bool(train_ids & test_ids) or metadata.get("cv_folds", 0) < 2
            or any(not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1 for score in metrics)):
        raise ValueError("A public release needs a reviewed classifier evaluated on at least two separate holdout job ads. Train a qualifying model first.")
    if training_data_changed(metadata=metadata):
        raise ValueError("Reviewed labels have changed since evaluation. Retrain before preparing a release.")

    path = storage.ROOT / "models/competency_classifier.joblib"
    if not path.is_file():
        raise ValueError("Prepare the release on the computer that trained and saved this model.")
    model_bytes = path.read_bytes()
    if digest(model_bytes) != metadata.get("classifier_sha256"):
        raise ValueError("The local classifier does not match the evaluated run. Use the training computer or retrain first.")
    model = load_model(BytesIO(model_bytes))
    version, content = _browser_artifact(model, metadata)
    return {"version": version, "content": content, "name": metadata["model_name"],
            "trained_at": metadata["training_timestamp"], "test_ads": len(test_ids), "macro_f1": metadata["macro_f1"],
            "vocabulary": "\n".join(model.named_steps["tfidf"].get_feature_names_out()) + "\n"}


def _github(session, method, path, *, allow_missing=False, **kwargs):
    try:
        response = session.request(method, f"https://api.github.com/repos/{REPOSITORY}/{path}",
                                   timeout=(5, 40), allow_redirects=False, **kwargs)
    except requests.RequestException as exc:
        raise ValueError("GitHub could not confirm the release. Check the repository before retrying.") from exc
    if method == "PATCH" and response.status_code in (409, 422):
        raise ValueError("GitHub could not advance main. Another change may have landed or the branch may require approval.")
    if response.status_code not in (200, 201) and not (allow_missing and response.status_code == 404):
        raise ValueError(f"GitHub did not confirm the release (HTTP {response.status_code}). Check repository access and branch permissions.")
    return response


def _bump_version(config):
    pattern = r'(?m)^VERSION = "(\d+)\.(\d+)\.(\d+)"(?=\r?$)'
    updated, count = re.subn(pattern, lambda value: f'VERSION = "{value[1]}.{value[2]}.{int(value[3]) + 1}"', config)
    if count != 1:
        raise ValueError("Could not read the app version on GitHub. The release was not written.")
    return updated


def publish_release(version):
    release = prepare_release()
    token = supabase_store._setting(TOKEN_SETTING)
    if not token:
        raise ValueError(f"Set {TOKEN_SETTING} on the private workspace before publishing.")
    if release["version"] != version:
        raise ValueError("The selected classifier changed. Prepare and review a new release.")

    with requests.Session() as session:
        session.headers.update(Authorization=f"Bearer {token}", Accept="application/vnd.github+json")
        ref = f"heads/{BRANCH}"
        head = _github(session, "GET", f"git/ref/{ref}").json()["object"]["sha"]
        raw_file = {"params": {"ref": head}, "headers": {"Accept": "application/vnd.github.raw+json"}}
        current = _github(session, "GET", "contents/" + MODEL_PATH, allow_missing=True, **raw_file)
        if current.status_code == 200:
            try:
                published = current.json()
                previous_run = None if published == {"schema": 0} else datetime.fromisoformat(published["trainedAt"])
            except (ValueError, TypeError, KeyError) as exc:
                raise ValueError("The existing public classifier could not be verified. Check model.json in GitHub before publishing.") from exc
            if published.get("version") == version:
                return None
            if previous_run is not None and previous_run >= datetime.fromisoformat(release["trained_at"]):
                raise ValueError("A newer evaluated classifier is already published.")
        _github(session, "GET", "contents/public-web/site/model.js", **raw_file)
        config = _github(session, "GET", "contents/" + CONFIG_PATH, **raw_file).content.decode("utf-8")
        files = {MODEL_PATH: release["content"].decode("utf-8"), CONFIG_PATH: _bump_version(config)}
        base = _github(session, "GET", f"git/commits/{head}").json()["tree"]["sha"]
        tree = _github(session, "POST", "git/trees", json={"base_tree": base, "tree": [
            {"path": path, "mode": "100644", "type": "blob", "content": content} for path, content in files.items()
        ]}).json()["sha"]
        commit = _github(session, "POST", "git/commits", json={
            "message": f"Release public classifier {version}", "tree": tree, "parents": [head],
        }).json()["sha"]
        _github(session, "PATCH", f"git/refs/{ref}", json={"sha": commit, "force": False})
        return commit
