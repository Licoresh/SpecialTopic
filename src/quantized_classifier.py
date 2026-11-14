"""CPU inference for the pinned MiniLM/BGE-M3 INT8 deployment bundle."""
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import urllib.request

import joblib
import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin

from .config import ROOT

MODEL_NAME = 'MiniLM + BGE-M3 INT8 ONNX (linear SVC)'
BUNDLE = ROOT / 'data/reference/semantic_int8'


def _weights(name, spec):
    local = os.environ.get('FOW_INT8_ENCODER_DIR')
    if local:
        return Path(local) / name / 'onnx/model_quint8_avx2.onnx'
    cache = Path(os.environ.get('FOW_MODEL_CACHE', Path.home() / '.cache/future_of_work'))
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / (spec['sha256'] + '.onnx')
    if not target.exists():
        from filelock import FileLock
        with FileLock(str(target) + '.lock'):
            if not target.exists():
                temporary = target.with_suffix('.download')
                h = hashlib.sha256()
                try:
                    with urllib.request.urlopen(spec['url'], timeout=120) as source, temporary.open('wb') as dest:
                        for chunk in iter(lambda: source.read(1024 * 1024), b''):
                            h.update(chunk)
                            dest.write(chunk)
                    if h.hexdigest() != spec['sha256']:
                        raise ValueError('Encoder download checksum mismatch.')
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
    return target


@lru_cache(maxsize=2)
def _encoder(name):
    import onnxruntime as ort
    from tokenizers import Tokenizer
    manifest = json.loads((BUNDLE / 'manifest.json').read_text())
    spec = manifest['encoders'][name]
    tokenizer_path = BUNDLE / name / 'tokenizer.json'
    if hashlib.sha256(tokenizer_path.read_bytes()).hexdigest() != manifest['tokenizer_sha256'][name]:
        raise ValueError('Tokenizer checksum mismatch.')
    tokenizer = Tokenizer.from_file(str(tokenizer_path))
    tokenizer.enable_truncation(max_length=spec['max_length'])
    tokenizer.enable_padding(pad_id=spec['pad_id'], pad_token=spec['pad_token'])
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    options.inter_op_num_threads = 1
    session = ort.InferenceSession(str(_weights(name, spec)), sess_options=options,
                                   providers=['CPUExecutionProvider'])
    return tokenizer, session, spec


def encode_phrases(phrases):
    texts = [str(p).strip() for p in phrases]
    if not texts:
        return np.empty((0, 1408), dtype=np.float32)
    order = np.argsort([-len(p) for p in texts])
    inverse = np.argsort(order)
    vectors = []
    for name in ('minilm', 'bge'):
        tokenizer, session, spec = _encoder(name)
        output = []
        input_names = {i.name for i in session.get_inputs()}
        for start in range(0, len(texts), 16):
            encoded = tokenizer.encode_batch([texts[i] for i in order[start:start+16]])
            inputs = {'input_ids': np.asarray([p.ids for p in encoded], dtype=np.int64),
                      'attention_mask': np.asarray([p.attention_mask for p in encoded], dtype=np.int64)}
            if 'token_type_ids' in input_names:
                inputs['token_type_ids'] = np.asarray([p.type_ids for p in encoded], dtype=np.int64)
            hidden = session.run(None, inputs)[0]
            if spec['pooling'] == 'cls':
                pooled = hidden[:, 0]
            else:
                mask = inputs['attention_mask'][..., None].astype(np.float32)
                pooled = (hidden * mask).sum(axis=1) / np.maximum(mask.sum(axis=1), 1e-9)
            pooled /= np.maximum(np.linalg.norm(pooled, axis=1, keepdims=True), 1e-12)
            output.append(pooled)
        vectors.append(np.concatenate(output)[inverse])
    return np.column_stack(vectors) / np.sqrt(2)


def prepare_runtime():
    """Download once and load both CPU encoders before processing the upload."""
    for name in ('minilm', 'bge'):
        _encoder(name)


class QuantizedSkillEmbeddings(TransformerMixin, BaseEstimator):
    def fit(self, X, y=None):
        return self

    def transform(self, X):
        return encode_phrases(X)


@lru_cache(maxsize=1)
def load_final_model():
    manifest = json.loads((BUNDLE / 'manifest.json').read_text())
    path = BUNDLE / 'classifier.joblib'
    if hashlib.sha256(path.read_bytes()).hexdigest() != manifest['classifier_sha256']:
        raise ValueError('Final classifier checksum mismatch.')
    model = joblib.load(path)
    model.name = model.research_model_name_ = MODEL_NAME
    model.version = manifest['version']
    model.trained_at = manifest['trained_at']
    model.release_status = 'exploratory'
    model.release_note = 'Evaluated on the reused study phrase holdout; nested validation is internal.'
    return model
