from functools import lru_cache

import pytest

from src import quantized_classifier as classifier


class BatchModel:
    def __init__(self):
        self.calls = 0

    def predict(self, phrases):
        self.calls += 1
        return [f'{len(phrases)}:{phrase}' for phrase in phrases]


@pytest.fixture
def released(monkeypatch):
    model = BatchModel()

    @lru_cache(maxsize=1)
    def load():
        return model

    load()
    monkeypatch.setattr(classifier, 'load_final_model', load)
    classifier._released_predictions.cache_clear()
    yield model
    classifier._released_predictions.cache_clear()


def test_release_cache_preserves_complete_batch_context(released):
    assert classifier.predict_batch(released, ['sql', 'python']) == ('2:sql', '2:python')
    assert classifier.predict_batch(released, ['sql', 'python']) == ('2:sql', '2:python')
    assert released.calls == 1
    assert classifier.predict_batch(released, ['python', 'sql']) == ('2:python', '2:sql')
    assert classifier.predict_batch(released, ['sql']) == ('1:sql',)
    assert released.calls == 3


def test_experimental_models_are_not_cached(released):
    other = BatchModel()
    classifier.predict_batch(other, ['sql'])
    classifier.predict_batch(other, ['sql'])
    assert other.calls == 2
    assert released.calls == 0


def test_cache_does_not_retain_oversized_requests(released):
    for _ in range(2):
        assert len(classifier.predict_batch(released, ['sql'] * 257)) == 257
    assert released.calls == 2
    assert classifier._released_predictions.cache_info().currsize == 0
