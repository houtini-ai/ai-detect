"""
Pattern diagnostics and text metrics — pure Python, no ML dependencies.

These heuristics explain *why* a neural detector flags a sentence. They are
derived from 70+ paired sentence tests against desklib/ai-text-detector-v1.01
(see docs/detection-patterns.md). They do not decide the AI/Human label — the
model does that — they annotate sentences with human-readable reasons and
concrete rewrite suggestions.

Each finding is ``{pattern, match, suggestion, start, end}``; ``start``/``end``
are character offsets into the sentence, for highlighting.
"""

import math
import re

from .text import sent_tokenize  # noqa: F401  (re-exported: the old public home)

# ---------------------------------------------------------------------------
# Pattern data — sourced from paired sentence tests (see docs/detection-patterns.md)
# ---------------------------------------------------------------------------

CONTRACTION_MAP = {
    "is not": "isn't", "are not": "aren't", "was not": "wasn't",
    "has not": "hasn't", "have not": "haven't", "had not": "hadn't",
    "does not": "doesn't", "do not": "don't", "did not": "didn't",
    "will not": "won't", "would not": "wouldn't", "could not": "couldn't",
    "should not": "shouldn't", "cannot": "can't", "can not": "can't",
    "it is": "it's", "that is": "that's", "there is": "there's",
    "it has": "it's", "that has": "that's",
    "they have": "they've", "we have": "we've", "you have": "you've",
    "they are": "they're", "we are": "we're", "you are": "you're",
}
# "has"/"have" only contract when they are auxiliaries ("it has been", "we have
# seen"), never when they mean "own" ("it has three ports").
_AUXILIARY_ONLY = {"it has", "that has", "they have", "we have", "you have"}
_PARTICIPLE = (r"(?:been|got|gotten|become|gone|done|made|taken|seen|had|shown|grown|"
               r"known|given|come|built|found|kept|left|lost|put|run|set|told|"
               r"(?:already|just|never|always|also|now|since|long|recently)\s+\w+|\w+ed)")

# base form -> suggestion. Every inflection (provide/provides/provided/providing)
# and both -ize and -ise spellings are matched.
FORMAL_VERBS = {
    "provide": "try 'gives you' or 'has'",
    "offer": "try 'has' or 'comes with'",
    "deliver": "try 'gives you' or just describe what it does",
    "encompass": "try 'covers' or 'includes'",
    "feature": "try 'has' or 'comes with'",
    "utilize": "try 'uses'",
    "represent": "try 'is' or rephrase",
    "demonstrate": "try 'shows'",
    "ensure": "try 'makes sure' or rephrase",
    "facilitate": "try 'makes it easy to' or 'helps'",
    "enable": "try 'lets you' or 'means you can'",
    "comprise": "try 'includes' or 'is made up of'",
    "implement": "try 'uses' or 'adds'",
    "incorporate": "try 'includes' or 'has'",
    "address": "try 'fixes' or 'deals with'",
    "achieve": "try 'gets' or 'hits'",
    "maintain": "try 'keeps'",
    "enhance": "try 'improves' or 'makes better'",
    "optimize": "try 'improves' or 'tweaks'",
    "operate": "try 'runs' or 'works'",
}
# These are just as often nouns ("new features", "email addresses", "special
# offers"). Only count them as verbs when the words either side say so.
_NOUN_OR_VERB = {"feature", "address", "offer"}
_NOUN_CUE_BEFORE = (r"(?:a|an|the|this|that|these|those|its|their|our|your|his|her|my|new|key|"
                    r"main|many|several|some|few|more|most|other|all|both|no|of|with|and|or|"
                    r"special|email|ip|web|two|three|four|five|six|\d+|"
                    r"\w+(?:ive|ous|ful|ble|al|ic|ed|ing|ty))")
_VERB_CUE_AFTER = (r"(?:a|an|the|this|that|these|those|its|their|our|your|his|her|up|over|"
                   r"more|several|many|multiple|numerous|some|all|both|you|users|\d+|"
                   r"\w+(?:ive|ent|ant|ous|ful|ble|ed|ing|al|ic))")

# Matched at start of sentence (case-insensitive)
FORMAL_TRANSITIONS = [
    ("Additionally", "cut it, or use 'And' / 'Plus'"),
    ("Furthermore", "cut it, or use 'And' / 'On top of that'"),
    ("Moreover", "cut it, or use 'And' / 'Also'"),
    ("In conclusion", "cut it, or use 'Look' / 'Bottom line'"),
    ("Consequently", "try 'So' or just state the result"),
    ("Nevertheless", "try 'Still' or 'That said'"),
    ("Nonetheless", "try 'Still' or 'Even so'"),
    ("Subsequently", "try 'Then' or 'After that'"),
    ("Conversely", "try 'On the other hand' or rephrase"),
    ("In terms of", "cut it — just name the thing"),
]

# Matched anywhere (case-insensitive, whole phrase)
FORMAL_TRANSITION_PHRASES = [
    ("It's important to note that", "cut it — just state the fact"),
    ("It's worth noting that", "cut it — just state the fact"),
    ("It is important to note", "cut it — just state the fact"),
    ("It is worth noting", "cut it — just state the fact"),
    ("This represents a significant", "rephrase — e.g. 'This is a big'"),
    ("This represents a major", "rephrase — e.g. 'This is a big'"),
]

AI_SLOP = [
    "delve", "leverage", "unlock", "seamless", "robust",
    "cutting-edge", "game-changer", "revolutionize", "groundbreaking",
    "elevate", "empower", "synergy", "paradigm", "holistic",
    "innovative", "strategic", "streamline", "landscape",
    "tapestry", "multifaceted", "spearhead", "underscore",
    "realm", "foster", "crucially", "notably", "remarkably",
]

VAGUE_ABSTRACTIONS = [
    ("several leading", "name them"),
    ("a wide range of", "name the range or drop it"),
    ("a range of", "name the range or drop it"),
    ("a variety of", "be specific"),
    ("a number of", "say how many, or name them"),
    ("various", "be specific — what exactly?"),
    ("numerous", "say how many, or name them"),
    ("multiple", "say how many, or name them"),
]

FLAGGY_ADVERBS = {
    "noticeably": "try 'definitely' or cut it",
    "significantly": "try 'a lot' or 'massively' or cut it",
    "comprehensively": "try 'fully' or cut it",
    "effectively": "often filler — cut it or say what it actually does",
    "particularly": "often filler — try 'especially' or cut it",
    "fundamentally": "often filler — cut it or say how",
    "substantially": "try 'a lot' or 'way more'",
    "predominantly": "try 'mostly'",
    "inherently": "often filler — cut it or explain why",
}

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "ʼ": "'"})


def _inflected(word):
    """A regex fragment matching a word and its regular inflections, in both
    -ize and -ise spellings."""
    stem = re.escape(word[:-1] if word.endswith("e") else word)
    stem = stem.replace("iz", "i[sz]")
    if word.endswith("e"):
        return stem + r"(?:e|es|ed|ing)"
    if word.endswith("s"):
        return stem + r"(?:es|ed|ing)?"
    return stem + r"(?:s|es|ed|ing)?"


_FORMAL_VERB_RX = {
    base: re.compile(r"\b" + _inflected(base) + r"\b", re.IGNORECASE)
    for base in FORMAL_VERBS
}
_SLOP_RX = [(w, re.compile(r"\b" + _inflected(w) + r"\b", re.IGNORECASE)) for w in AI_SLOP]
_CONTRACTION_RX = {
    phrase: re.compile(
        r"\b" + re.escape(phrase) + r"\b"
        + (r"(?=\s+" + _PARTICIPLE + r"\b)" if phrase in _AUXILIARY_ONLY else ""),
        re.IGNORECASE)
    for phrase in CONTRACTION_MAP
}
_VAGUE_RX = [(p, s, re.compile(r"\b" + re.escape(p) + r"\b", re.IGNORECASE))
             for p, s in VAGUE_ABSTRACTIONS]
_ADVERB_RX = {a: re.compile(r"\b" + a + r"\b", re.IGNORECASE) for a in FLAGGY_ADVERBS}
_FOR_WHO_RX = re.compile(r"^For\s+\w+[\w\s]*?\s+who\s+")
_NOUN_BEFORE_RX = re.compile(r"\b" + _NOUN_CUE_BEFORE + r"\s+$", re.IGNORECASE)
_VERB_AFTER_RX = re.compile(r"^\s+" + _VERB_CUE_AFTER + r"\b", re.IGNORECASE)


def _is_verb_use(text, match):
    """For words that are nouns as often as verbs: a determiner or adjective in
    front means noun; an object-like word behind means verb."""
    if _NOUN_BEFORE_RX.search(text[:match.start()]):
        return False
    return bool(_VERB_AFTER_RX.match(text[match.end():]))


def diagnose_sentence(text):
    """Check a sentence for patterns that tend to trigger AI detection.

    Returns a list of {pattern, match, suggestion, start, end} findings.
    """
    findings = []
    text = text.translate(_APOSTROPHES)  # same length, so offsets still hold
    lower = text.lower()

    def add(pattern, match, suggestion, start, end):
        findings.append({"pattern": pattern, "match": match, "suggestion": suggestion,
                         "start": start, "end": end})

    # 1. Missing contractions
    for phrase, contraction in CONTRACTION_MAP.items():
        m = _CONTRACTION_RX[phrase].search(text)
        if m:
            add("missing_contraction", phrase, f"use '{contraction}'", m.start(), m.end())

    # 2. Formal verbs, any inflection
    for base, suggestion in FORMAL_VERBS.items():
        for m in _FORMAL_VERB_RX[base].finditer(text):
            if base in _NOUN_OR_VERB and not _is_verb_use(text, m):
                continue
            add("formal_verb", m.group(0).lower(), suggestion, m.start(), m.end())
            break

    # 3. Formal transitions at start of sentence
    for transition, suggestion in FORMAL_TRANSITIONS:
        if lower.startswith(transition.lower()):
            add("formal_transition", transition, suggestion, 0, len(transition))
            break  # only one start-of-sentence match

    # 4. Formal transition phrases anywhere
    for phrase, suggestion in FORMAL_TRANSITION_PHRASES:
        at = lower.find(phrase.lower())
        if at >= 0:
            add("formal_transition", phrase, suggestion, at, at + len(phrase))

    # 5. "For X who Y" AI frame
    m = _FOR_WHO_RX.match(text)
    if m:
        add("ai_frame", "For [X] who [Y]", "try 'If you...' or a direct statement",
            m.start(), m.end())

    # 6. AI slop words, any inflection
    for _word, rx in _SLOP_RX:
        m = rx.search(text)
        if m:
            add("ai_slop", m.group(0).lower(), "replace with plain English", m.start(), m.end())

    # 7. Vague abstractions (longest phrase wins: "a wide range of" not also "a range of")
    taken = []
    for phrase, suggestion, rx in _VAGUE_RX:
        m = rx.search(text)
        if m and not any(s <= m.start() < e for s, e in taken):
            taken.append((m.start(), m.end()))
            add("vague_abstraction", phrase, suggestion, m.start(), m.end())

    # 8. Flaggy adverbs
    for adverb, suggestion in FLAGGY_ADVERBS.items():
        m = _ADVERB_RX[adverb].search(text)
        if m:
            add("flaggy_adverb", adverb, suggestion, m.start(), m.end())

    return findings


def calculate_sdsl(sentences):
    """Sentence-length standard deviation and coefficient of variation.

    Uniform sentence length is a weak but real AI signal — humans vary their
    rhythm more. Returns mean/stddev/cv and a plain-English verdict.
    """
    if not sentences:
        return {"mean": 0, "stddev": 0, "cv": 0, "verdict": "no text"}

    lengths = [len(s.split()) for s in sentences]
    n = len(lengths)
    mean = sum(lengths) / n
    if n < 2 or mean == 0:
        return {"mean": round(mean, 1), "stddev": 0, "cv": 0, "verdict": "too short to measure"}

    variance = sum((length - mean) ** 2 for length in lengths) / n
    stddev = math.sqrt(variance)
    cv = stddev / mean

    if cv < 0.3:
        verdict = "very uniform (AI-like)"
    elif cv < 0.5:
        verdict = "somewhat uniform"
    else:
        verdict = "natural variation"

    return {
        "mean": round(mean, 1),
        "stddev": round(stddev, 1),
        "cv": round(cv, 2),
        "verdict": verdict,
        "sentence_count": n,
        "lengths": lengths,
    }


def count_pattern_totals(sentences_data, only_label=None):
    """Summarise pattern counts across sentences. ``only_label="AI"`` counts
    just the findings on AI-labelled sentences (the ones the CLI prints)."""
    totals = {}
    for r in sentences_data:
        if r is None or (only_label and r.get("label") != only_label):
            continue
        for d in r.get("diagnostics", []):
            p = d["pattern"]
            totals[p] = totals.get(p, 0) + 1
    return totals
