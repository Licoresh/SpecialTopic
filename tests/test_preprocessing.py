from src.preprocessing import extract_candidate_phrases


def test_progress_preserves_candidate_output():
    texts = ["Synthetic Python statistical analysis", "Synthetic SQL programming", "Synthetic Python statistical analysis"]
    events = []
    expected = extract_candidate_phrases(texts)
    actual = extract_candidate_phrases(texts, progress=lambda value, message: events.append((value, message)))
    assert actual == expected
    assert len(events) == 2
    assert "2 of 2" in events[-1][1]

def test_ngrams_lemmas_and_technical_tokens():
    text = "Models use C++ C# .NET R SQL and machine learning."
    result = extract_candidate_phrases([text, text])
    assert len(result) == 1
    phrases = {p[0] for p in result[text]["phrases"]}
    assert {"C++", "C#", ".NET", "R", "SQL", "machine learning"} <= phrases
    assert "model" in result[text]["lemmas"]

def test_stopwords_and_candidate_limit():
    result = extract_candidate_phrases(["Python learning for data analysis"], stopwords=["python"], max_candidates=2)
    values = next(iter(result.values()))
    assert values["truncated"]
    assert "Python" not in {p[0] for p in values["phrases"]}


def test_extraction_drops_connector_fragments_and_prioritizes_research_terms():
    text = "With strong written and spoken English, a keen eye for data analysis and Python skills."
    result = extract_candidate_phrases([text], max_candidates=3, priority_phrases=["data analysis", "python"])
    phrases = [item[0] for item in result[text]["phrases"]]
    assert "data analysis" in phrases
    assert "Python" in phrases
    assert not {"with strong", "written and", "and spoken", "a keen", "eye for"}.intersection(phrases)


def test_long_document_keeps_original_phrase_spans_and_order():
    from src.preprocessing import get_nlp, extract_ngrams
    sentence = "Models  use C++ for café data analysis.\n"
    nlp = get_nlp()
    single = extract_ngrams(nlp(sentence))
    repeated = sentence * 40
    actual = extract_ngrams(nlp(repeated))
    expected = [(phrase, normal, start + offset * len(sentence), end + offset * len(sentence))
                for offset in range(40) for phrase, normal, start, end in single]
    assert actual == expected
    assert all(repeated[start:end] == phrase for phrase, _, start, end in actual)
    assert any(phrase == "C++" for phrase, _, _, _ in actual)
