from functools import lru_cache
import re
from .cleaning import clean_text, normalize_text

TECH = re.compile(r"(?<!\w)(?:C\+\+|C#|\.NET)(?!\w)", re.I)
EXTRACTION_VERSION = 2

@lru_cache(maxsize=1)
def get_nlp():
    import spacy
    from spacy.symbols import ORTH
    nlp = spacy.blank("en")
    nlp.add_pipe("sentencizer")
    nlp.add_pipe("lemmatizer", config={"mode": "lookup"})
    nlp.initialize()
    for word in ("C++", "c++", "C#", "c#", ".NET", ".net"):
        nlp.tokenizer.add_special_case(word, [{ORTH: word}])
    nlp.max_length = 5_000_000
    return nlp

def extract_ngrams(doc, stopwords=(), max_n=3):
    blocked = set(stopwords)
    results = []
    for sentence in doc.sents:
        tokens = list(sentence)
        for n in range(1, max_n + 1):
            for start in range(len(tokens) - n + 1):
                group = tokens[start:start+n]
                if any(t.is_space or t.is_punct for t in group):
                    continue
                # Do not offer connector-led/trailing fragments such as
                # "with strong", "written and", or "eye for" for labeling.
                if n > 1 and (group[0].is_stop or group[-1].is_stop
                              or group[0].text.casefold() in blocked
                              or group[-1].text.casefold() in blocked):
                    continue
                if all(t.is_stop or t.text.casefold() in blocked or t.like_num for t in group):
                    continue
                if n == 1 and (group[0].is_stop or group[0].text.casefold() in blocked):
                    continue
                phrase = doc.text[group[0].idx:group[-1].idx + len(group[-1])]
                normalized = " ".join((t.lemma_ or t.text).casefold() for t in group)
                results.append((phrase, normalized, group[0].idx, group[-1].idx + len(group[-1])))
    return results

def extract_candidate_phrases(texts, stopwords=(), batch_size=64, max_candidates=300, priority_phrases=()):
    unique = list(dict.fromkeys(clean_text(t) for t in texts))
    priorities = {normalize_text(phrase) for phrase in priority_phrases}
    output = {}
    from .background_tasks import checkpoint
    checkpoint()
    for text, doc in zip(unique, get_nlp().pipe(unique, batch_size=batch_size)):
        checkpoint()
        candidates = extract_ngrams(doc, stopwords)
        seen = set()
        retained = []
        for item in candidates:
            if item[1] not in seen:
                retained.append(item)
                seen.add(item[1])
        # Exact research vocabulary (for example SQL or data analysis) comes
        # first, followed by multiword candidates, then single tokens. The
        # former n-gram loop exhausted the per-ad cap on unigrams before it
        # reached useful phrases near the beginning of longer job ads.
        retained.sort(key=lambda item: (
            0 if item[1] in priorities or normalize_text(item[0]) in priorities
            else 1 if len(item[1].split()) > 1 else 2,
            -len(item[1].split()),
            item[2],
        ))
        output[text] = {"phrases": retained[:max_candidates], "truncated": len(retained) > max_candidates,
                        "lemmas": " ".join((t.lemma_ or t.text).casefold() for t in doc if not t.is_space)}
    return output
