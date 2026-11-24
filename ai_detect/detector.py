"""
Model loading, caching and the scoring pipeline.

``classify_text()`` is the stable public entry point: one model, the report
shape the CLI and MCP tools have always returned, plus additive keys. Under it,
``score_document()`` scores a parsed Document with any number of loaded
backends; ``ensemble.py`` combines several.

Two kinds of score are produced, and they are kept apart:

* per sentence: each prose sentence of five words or more, scored on its own.
  Useful for pointing at lines, but every detector here was trained on whole
  documents, so a single sentence is out of distribution.
* per passage: consecutive sentences packed into windows of about 200 words,
  scored as the detectors were trained to be used. The document score is the
  word-weighted mean of the passage scores.
"""

import sys
import threading

from .backends import (  # noqa: F401  (re-exported)
    BATCH_SIZE,
    MissingRuntimeError,
    device_pref,
    load_backend,
    resolve_torch_device,
)
from .models import DEFAULT_MODEL, MODELS, REGISTRY
from .patterns import calculate_sdsl, count_pattern_totals, diagnose_sentence
from .registry import UnknownModelError  # noqa: F401
from .text import PROSE_KINDS, Document, parse_text, split_sentences

MIN_WORDS = 5          # sentences below this are skipped (fragments: too short to score)
PASSAGE_WORDS = 200    # target window for document-level scoring
SHORT_PASSAGE = 60     # below this a passage score is marked unreliable

# Back-compat names from the two-model registry.
DESKLIB_MODEL = MODELS["desklib"].repo
LIGHT_REPO = MODELS["light"].repo
LIGHT_ONNX_FILE = MODELS["light"].cache_probe


def verdict(pct):
    """Map an overall AI percentage to a plain-English verdict (single source of truth)."""
    return "LIKELY AI" if pct > 50 else "LIKELY HUMAN" if pct < 40 else "MIXED"


def preload_dependencies():
    """Import the heavy backend libraries in the calling (ideally main) thread.

    Importing numpy / onnxruntime / torch / transformers for the FIRST time from
    inside a running server — in the event-loop thread or a worker thread it
    dispatches to — can deadlock on the import machinery. Calling this once at
    startup makes every later import a cheap sys.modules hit. Missing optional
    deps (e.g. onnxruntime) are ignored.
    """
    import importlib
    for mod in ("numpy", "torch", "onnxruntime", "tokenizers", "huggingface_hub"):
        try:
            importlib.import_module(mod)
        except Exception:
            pass
    try:
        from transformers import (  # noqa: F401
            AutoConfig, AutoModel, AutoModelForSequenceClassification,
            AutoTokenizer, PreTrainedModel,
        )
    except Exception:
        pass


def _announce_download(spec):
    print(
        f"First run with '{spec.label}': downloading ~{spec.approx_mb} MB "
        f"from Hugging Face (cached in ~/.cache/huggingface for next time)...",
        file=sys.stderr,
    )


def is_model_cached(model_name):
    """Whether a model's weights are already in the local HF cache.

    Cheap: probes one representative large file. Returns False for unknown
    models or if huggingface_hub can't answer.
    """
    try:
        spec = REGISTRY.resolve(model_name)
    except ValueError:
        return False
    try:
        from huggingface_hub import try_to_load_from_cache
        return isinstance(try_to_load_from_cache(spec.repo, spec.cache_probe), str)
    except Exception:
        return False


def prefetch_model(model_name=DEFAULT_MODEL):
    """Download a model's files into the local HF cache WITHOUT loading it.

    Only the files the spec lists are fetched. No-op if already cached. Never
    raises: on a network or hub error it logs and returns False, and the first
    detect call downloads the normal way.
    """
    try:
        spec = REGISTRY.resolve(model_name)
    except ValueError:
        return False
    if is_model_cached(spec.id):
        return True
    try:
        from huggingface_hub import snapshot_download
    except Exception:
        return False
    _announce_download(spec)
    try:
        snapshot_download(spec.repo, allow_patterns=list(spec.files))
        for repo, files in spec.extra_repos:
            snapshot_download(repo, allow_patterns=list(files))
    except Exception as e:  # network, auth, hub outage — stay non-fatal
        print(f"ai-detect: model prefetch failed ({e}); the first detect call "
              "will download it instead.", file=sys.stderr)
        return False
    return is_model_cached(spec.id)


_DETECTOR_CACHE = {}
# Guards construction only: two concurrent first calls for the same model would
# otherwise each load a copy. Per-key, so different models can load in parallel.
_DETECTOR_LOCKS = {}
_DETECTOR_LOCKS_GUARD = threading.Lock()


def get_detector(model=DEFAULT_MODEL, device=None):
    """Return a cached backend for a model id or alias."""
    spec = REGISTRY.resolve(model)
    key = (spec.id, device_pref(device))

    cached = _DETECTOR_CACHE.get(key)  # fast path: no lock once loaded
    if cached is not None:
        return cached

    with _DETECTOR_LOCKS_GUARD:
        lock = _DETECTOR_LOCKS.setdefault(key, threading.Lock())
    with lock:
        if key not in _DETECTOR_CACHE:  # re-check: another thread may have won
            if not is_model_cached(spec.id):
                _announce_download(spec)
            _DETECTOR_CACHE[key] = load_backend(spec, device=device)
    return _DETECTOR_CACHE[key]


def unload_detector(model, device=None):
    """Drop a cached backend so its memory can be reclaimed (used when an
    ensemble loads models one at a time)."""
    try:
        spec = REGISTRY.resolve(model)
    except ValueError:
        return False
    return _DETECTOR_CACHE.pop((spec.id, device_pref(device)), None) is not None


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def to_document(source):
    """Accept a Document or raw text; return a Document."""
    return source if isinstance(source, Document) else parse_text(source or "")


def sentence_rows(document):
    """Flatten a Document into sentence rows: every prose sentence, plus each
    heading as a row that is never scored."""
    rows = []
    for block_index, block in enumerate(document.blocks):
        if block.kind == "heading":
            pieces, scoreable = [block.text], False
        elif block.kind in PROSE_KINDS:
            pieces, scoreable = split_sentences(block.text), True
        else:
            continue
        for piece in pieces:
            rows.append({
                "index": len(rows), "block": block_index, "kind": block.kind,
                "sentence": piece,
                "scoreable": scoreable and len(piece.split()) >= MIN_WORDS,
            })
    return rows


def build_passages(rows):
    """Pack consecutive scoreable-kind sentences into ~PASSAGE_WORDS windows.
    A heading closes the current window, so a passage never spans sections."""
    passages, current, words = [], [], 0

    def close():
        nonlocal current, words
        if current:
            passages.append({"start": current[0], "end": current[-1], "words": words})
        current, words = [], 0

    for row in rows:
        if row["kind"] == "heading":
            close()
            continue
        n = len(row["sentence"].split())
        if current and words + n > PASSAGE_WORDS * 1.25:
            close()
        current.append(row["index"])
        words += n
        if words >= PASSAGE_WORDS:
            close()
    close()
    # A short tail reads better merged into the passage before it.
    if len(passages) > 1 and passages[-1]["words"] < SHORT_PASSAGE:
        tail = passages.pop()
        last = passages[-1]
        if all(r["kind"] != "heading" for r in rows[last["end"]:tail["start"]]):
            last["end"], last["words"] = tail["end"], last["words"] + tail["words"]
        else:
            passages.append(tail)
    return passages


def score_document(document, detectors, progress=None):
    """Score a Document with one or more loaded backends.

    detectors: ordered mapping {model id: backend}. Returns
    ``(rows, passages)`` where every scoreable row carries ``margins`` and
    ``scores`` dicts keyed by model id, and every passage likewise.
    ``progress(model_id, stage)`` is called before each model's work.
    """
    rows = sentence_rows(document)
    passages = build_passages(rows)
    scoreable = [r for r in rows if r["scoreable"]]
    for r in scoreable:
        r["margins"], r["scores"] = {}, {}
    passage_texts = [
        " ".join(r["sentence"] for r in rows[p["start"]:p["end"] + 1] if r["kind"] != "heading")
        for p in passages
    ]
    for p in passages:
        p["margins"], p["scores"] = {}, {}
        p["short"] = p["words"] < SHORT_PASSAGE

    for model_id, backend in detectors.items():
        if progress:
            progress(model_id, "scoring")
        texts = [r["sentence"] for r in scoreable] + passage_texts
        margins = _margins(backend, texts) if texts else []
        for r, m in zip(scoreable, margins):
            r["margins"][model_id] = round(m, 4)
            r["scores"][model_id] = round(_sigmoid(m), 4)
        for p, m in zip(passages, margins[len(scoreable):]):
            p["margins"][model_id] = round(m, 4)
            p["scores"][model_id] = round(_sigmoid(m), 4)
    return rows, passages


def _sigmoid(x):
    from .backends import sigmoid
    return sigmoid(x)


def _margins(backend, texts):
    """Logit margins from a backend. Anything that only implements the old
    ``score()`` contract (a test double, a third-party backend) still works."""
    if hasattr(backend, "margins"):
        return [float(m) for m in backend.margins(texts)]
    import math
    out = []
    for p in backend.score(texts):
        p = min(max(float(p), 1e-7), 1 - 1e-7)
        out.append(math.log(p / (1 - p)))
    return out


def weighted_pct(passages, key):
    """Word-weighted mean of a per-passage probability, as a percentage."""
    total = sum(p["words"] for p in passages)
    if not total:
        return 0.0
    return round(sum(p["words"] * key(p) for p in passages) / total * 100, 1)


def build_report(document, rows, passages, model_id, prob_of=None, label="model"):
    """Assemble the public report dict from scored rows.

    prob_of(row_or_passage) returns the probability to report; by default the
    raw probability of ``model_id``.
    """
    prob_of = prob_of or (lambda item: item["scores"][model_id])
    sentences, probs, ai_count = [], [], 0
    for r in rows:
        if not r["scoreable"]:
            sentences.append({
                "index": r["index"], "block": r["block"], "kind": r["kind"],
                "sentence": r["sentence"], "label": "Skipped", "confidence": 0.0,
                "ai_prob": 0.0, "human_prob": 0.0, "diagnostics": [],
            })
            continue
        ai_prob = float(prob_of(r))
        is_ai = ai_prob >= 0.5
        ai_count += is_ai
        probs.append(ai_prob)
        sentences.append({
            "index": r["index"], "block": r["block"], "kind": r["kind"],
            "sentence": r["sentence"],
            "label": "AI" if is_ai else "Human",
            "confidence": round(max(ai_prob, 1.0 - ai_prob), 4),
            "ai_prob": round(ai_prob, 4),
            "human_prob": round(1.0 - ai_prob, 4),
            "diagnostics": diagnose_sentence(r["sentence"]),
            "scores": dict(r["scores"]),
        })
    scored = [r["sentence"] for r in rows if r["scoreable"]]
    out_passages = [{
        "start": p["start"], "end": p["end"], "words": p["words"], "short": p["short"],
        "ai_prob": round(float(prob_of(p)), 4), "scores": dict(p["scores"]),
    } for p in passages]
    return {
        "sentences": sentences,
        "model_ai_pct": round(sum(probs) / len(probs) * 100, 1) if probs else 0.0,
        "ai_count": ai_count,
        "human_count": len(probs) - ai_count,
        "skipped_count": len(rows) - len(probs),
        "total": len(rows),
        "model": model_id if label == "model" else label,
        "models": sorted({m for r in rows if r["scoreable"] for m in r["scores"]}) or [model_id],
        "text_metrics": calculate_sdsl(scored),
        "pattern_totals": count_pattern_totals(sentences),
        "flagged_pattern_totals": count_pattern_totals(sentences, only_label="AI"),
        "document_ai_pct": weighted_pct(out_passages, lambda p: p["ai_prob"]),
        "passages": out_passages,
        "words": sum(len(s.split()) for s in scored),
        "blocks": [b.as_dict() for b in document.blocks],
    }


def classify_text(text, model=DEFAULT_MODEL, device=None, detector=None):
    """Classify each sentence with ONE model and return an aggregate report.

    ``text`` may be a string (plain text or Markdown) or a parsed Document.
    Returns per-sentence results (label, probabilities, diagnostics), the mean
    per-sentence AI %, counts, SDSL text metrics and pattern totals, as it
    always has, plus the document-level score (``document_ai_pct``,
    ``passages``) and the parsed ``blocks``.
    """
    if detector is None:
        detector = get_detector(model=model, device=device)
        model_id = REGISTRY.resolve(model).id
    else:
        model_id = getattr(detector, "name", model)
    document = to_document(text)
    rows, passages = score_document(document, {model_id: detector})
    return build_report(document, rows, passages, model_id)
