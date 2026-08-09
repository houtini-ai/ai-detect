"""
Pattern diagnostics and text metrics — pure Python, no ML dependencies.

These heuristics explain *why* the neural detector flags a sentence. They are
derived from 70+ paired sentence tests against desklib/ai-text-detector-v1.01
(see docs/detection-patterns.md). They do not decide the AI/Human label — the
model does that — they annotate flagged sentences with human-readable reasons
and concrete rewrite suggestions.
"""

import math
import re

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

FORMAL_VERBS = {
    "provides": "try 'gives you' or 'has'",
    "offers": "try 'has' or 'comes with'",
    "delivers": "try 'gives you' or just describe what it does",
    "encompasses": "try 'covers' or 'includes'",
    "features": "try 'has' or 'comes with'",
    "utilizes": "try 'uses'",
    "represents": "try 'is' or rephrase",
    "demonstrates": "try 'shows'",
    "ensures": "try 'makes sure' or rephrase",
    "facilitates": "try 'makes it easy to' or 'helps'",
    "enables": "try 'lets you' or 'means you can'",
    "comprises": "try 'includes' or 'is made up of'",
    "implements": "try 'uses' or 'adds'",
    "incorporates": "try 'includes' or 'has'",
    "addresses": "try 'fixes' or 'deals with'",
    "achieves": "try 'gets' or 'hits'",
    "maintains": "try 'keeps'",
    "enhances": "try 'improves' or 'makes better'",
    "optimizes": "try 'improves' or 'tweaks'",
    "operates": "try 'runs' or 'works'",
}

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
    "tapestry", "multifaceted", "spearhead", "underscores",
    "realm", "foster", "crucially", "notably", "remarkably",
]

VAGUE_ABSTRACTIONS = [
    ("several leading", "name them"),
    ("various", "be specific — what exactly?"),
    ("a range of", "name the range or drop it"),
    ("numerous", "say how many, or name them"),
    ("a number of", "say how many, or name them"),
    ("a variety of", "be specific"),
    ("a wide range of", "name the range or drop it"),
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


def diagnose_sentence(text):
    """Check a sentence for patterns that tend to trigger AI detection.

    Returns a list of {pattern, match, suggestion} findings.
    """
    findings = []
    lower = text.lower()

    # 1. Missing contractions
    for phrase, contraction in CONTRACTION_MAP.items():
        pattern = re.compile(r'\b' + re.escape(phrase) + r'\b', re.IGNORECASE)
        if pattern.search(text):
            findings.append({
                "pattern": "missing_contraction",
                "match": phrase,
                "suggestion": f"use '{contraction}'",
            })

    # 2. Formal verbs — match as whole words
    for verb, suggestion in FORMAL_VERBS.items():
        if re.search(r'\b' + re.escape(verb) + r'\b', lower):
            findings.append({
                "pattern": "formal_verb",
                "match": verb,
                "suggestion": suggestion,
            })

    # 3. Formal transitions at start of sentence
    for transition, suggestion in FORMAL_TRANSITIONS:
        if lower.startswith(transition.lower()):
            findings.append({
                "pattern": "formal_transition",
                "match": transition,
                "suggestion": suggestion,
            })
            break  # only one start-of-sentence match

    # 4. Formal transition phrases anywhere
    for phrase, suggestion in FORMAL_TRANSITION_PHRASES:
        if phrase.lower() in lower:
            findings.append({
                "pattern": "formal_transition",
                "match": phrase,
                "suggestion": suggestion,
            })

    # 5. "For X who Y" AI frame
    if re.match(r'^For\s+\w+[\w\s]*?\s+who\s+', text):
        findings.append({
            "pattern": "ai_frame",
            "match": "For [X] who [Y]",
            "suggestion": "try 'If you...' or a direct statement",
        })

    # 6. AI slop words
    for word in AI_SLOP:
        if re.search(r'\b' + re.escape(word) + r'\b', lower):
            findings.append({
                "pattern": "ai_slop",
                "match": word,
                "suggestion": "replace with plain English",
            })

    # 7. Vague abstractions
    for phrase, suggestion in VAGUE_ABSTRACTIONS:
        if phrase.lower() in lower:
            findings.append({
                "pattern": "vague_abstraction",
                "match": phrase,
                "suggestion": suggestion,
            })

    # 8. Flaggy adverbs
    for adverb, suggestion in FLAGGY_ADVERBS.items():
        if re.search(r'\b' + re.escape(adverb) + r'\b', lower):
            findings.append({
                "pattern": "flaggy_adverb",
                "match": adverb,
                "suggestion": suggestion,
            })

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

    variance = sum((l - mean) ** 2 for l in lengths) / n
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


def count_pattern_totals(sentences_data):
    """Summarise pattern counts across all scored sentences."""
    totals = {}
    for r in sentences_data:
        for d in r.get("diagnostics", []):
            p = d["pattern"]
            totals[p] = totals.get(p, 0) + 1
    return totals


def sent_tokenize(text):
    """Split text into sentences on ., !, ? boundaries."""
    return [s.strip() for s in re.split(r'(?<=[.!?])\s+', text.strip()) if s.strip()]
