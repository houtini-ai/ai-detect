"""The full analysis pipeline: load a source, score it, attach every signal.

    loaded = load_source(text=..., file=..., url=...)
    report = analyze(loaded, models=["desklib", "gpttrace-150m"])

One report holds four separate signals, and they are never mixed:

1. model scores  — per sentence and per passage, one model or an ensemble
2. sentence patterns — the pattern layer's findings and rewrite suggestions
3. structure and style tells — page-level habits (tells.py, visual.py)
4. perplexity and burstiness — optional readout from a small language model

``classify_text()`` in detector.py remains the stable single-model API; this
module is what the CLI, the MCP server and the web UI call.
"""

import os
from dataclasses import dataclass, field

from . import ensemble
from .detector import (
    DEFAULT_MODEL,
    _margins,
    _sigmoid,
    build_passages,
    build_report,
    get_detector,
    sentence_rows,
    unload_detector,
    verdict,
    weighted_pct,
)
from .fetch import fetch_html_file, fetch_url, is_url
from .models import REGISTRY
from .tells import find_tells
from .text import Document, parse_text
from .visual import find_visual_tells

MAX_FILE_BYTES = 20 * 1024 * 1024
SHORT_TEXT_WORDS = 150   # below this every detector's card calls the result unreliable


@dataclass
class Loaded:
    document: Document
    kind: str = "text"          # text | file | url
    label: str = ""             # file name, URL or "pasted text"
    visual: dict = field(default_factory=dict)
    screenshot: bytes = b""


def read_text_file(path):
    """Read a text file as UTF-8, falling back to Windows-1252 rather than
    failing on one stray byte."""
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No such file: {path}")
    if os.path.getsize(path) > MAX_FILE_BYTES:
        raise ValueError(f"{path} is larger than {MAX_FILE_BYTES // (1024 * 1024)} MB.")
    with open(path, "rb") as f:
        raw = f.read()
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("cp1252", errors="replace")


def load_source(text=None, file=None, url=None, timeout=30.0, screenshot=True):
    """Turn exactly one of text / file / url into a Loaded document.

    A ``text`` value that is nothing but an http(s) URL is fetched as one.
    ``.html`` / ``.htm`` files are rendered like a web page; any other file is
    read as plain text or Markdown.
    """
    given = [v for v in (text, file, url) if v]
    if len(given) != 1:
        raise ValueError("Give exactly one of: text, file, url.")
    if text and is_url(text.strip()):
        url, text = text.strip(), None
    if url:
        result = fetch_url(url, timeout=timeout, screenshot=screenshot)
        return Loaded(result.document, "url", result.url, result.visual, result.screenshot)
    if file:
        if file.lower().endswith((".html", ".htm")):
            result = fetch_html_file(file, timeout=timeout, screenshot=screenshot)
            result.document.source = "file"
            return Loaded(result.document, "file", file, result.visual, result.screenshot)
        document = parse_text(read_text_file(file), source="file")
        return Loaded(document, "file", file)
    return Loaded(parse_text(text, source="text"), "text", "pasted text")


def _score_all(document, model_ids, device, low_memory, progress):
    rows = sentence_rows(document)
    passages = build_passages(rows)
    scoreable = [r for r in rows if r["scoreable"]]
    for item in scoreable + passages:
        item["margins"], item["scores"] = {}, {}
    for p in passages:
        p["short"] = p["words"] < 60
    passage_texts = [
        " ".join(r["sentence"] for r in rows[p["start"]:p["end"] + 1] if r["kind"] != "heading")
        for p in passages
    ]
    texts = [r["sentence"] for r in scoreable] + passage_texts
    for n, model_id in enumerate(model_ids):
        if progress:
            progress({"stage": "loading", "model": model_id, "index": n, "of": len(model_ids)})
        backend = get_detector(model_id, device=device)
        if progress:
            progress({"stage": "scoring", "model": model_id, "index": n, "of": len(model_ids)})
        margins = _margins(backend, texts) if texts else []
        for item, m in zip(scoreable + passages, margins):
            item["margins"][model_id] = round(m, 4)
            item["scores"][model_id] = round(_sigmoid(m), 4)
        if low_memory and len(model_ids) > 1:
            unload_detector(model_id, device=device)
    return rows, passages


def assess(report, n_models=1):
    """A plain verdict with a stated confidence and its reasons.

    The label comes from the document-level (passage) score, which is how the
    detectors were trained to be used. Confidence drops for short text, for a
    score near the middle, and when the models disagree.
    """
    words = report.get("words", 0)
    # The calibrated document score: each model read at its own operating point.
    pct = report.get("operating_point", {}).get("calibrated_document_pct",
                                                report["document_ai_pct"])
    notes = []
    if words == 0:
        return {"label": "No prose to score", "ai_pct": 0.0, "confidence": "none",
                "basis": "document", "notes": ["Nothing long enough to score."],
                "breakdown": {"ai": 0, "uncertain": 0, "human": 0}}
    distance = abs(pct - 50)
    level = 2 if distance >= 35 else 1 if distance >= 15 else 0
    if words < SHORT_TEXT_WORDS:
        level = min(level, 0)
        notes.append(f"Only {words} words. The model cards call results under about "
                     f"{SHORT_TEXT_WORDS} words unreliable.")
    agreement = report.get("ensemble", {}).get("document_agreement")
    if agreement is not None and n_models > 1:
        split = min(agreement, n_models - agreement)
        if split:
            level = max(0, level - 1)
            notes.append(f"The models disagree: {agreement} of {n_models} call this document AI.")
        else:
            notes.append(f"All {n_models} models agree.")
    by_words = {"ai": 0, "uncertain": 0, "human": 0}
    for s in report["sentences"]:
        if s["label"] == "Skipped":
            continue
        n = len(s["sentence"].split())
        p = s.get("calibrated_prob", s["ai_prob"])
        key = "ai" if p >= 0.65 else "human" if p <= 0.35 else "uncertain"
        by_words[key] += n
    total = sum(by_words.values()) or 1
    breakdown = {k: round(v * 100 / total) for k, v in by_words.items()}
    if breakdown["ai"] >= 20 and breakdown["human"] >= 20:
        notes.append("Sentence scores are split, which can mean mixed authorship or "
                     "an edited draft. Single-sentence scores are a rough signal.")
    # Wider middle band than the legacy verdict(): near the operating point the
    # honest answer is that it cannot tell.
    label = "Likely AI" if pct > 60 else "Likely human" if pct < 40 else "Uncertain"
    return {"label": label, "ai_pct": pct, "basis": "document",
            "confidence": ("low", "moderate", "high")[level], "notes": notes,
            "breakdown": breakdown, "words": words}


def _explain(sentence, report, tells_by_block, perplexity):
    """Short reasons a reader can check, for one scored sentence."""
    why = []
    scores = sentence.get("scores", {})
    flags = sentence.get("flags")
    if flags:
        hot = [m for m, f in flags.items() if f]
        why.append(f"{len(hot)} of {len(flags)} models flag it"
                   + (": " + ", ".join(hot) if hot and len(hot) < len(flags) else "") + ".")
    elif scores:
        model, p = next(iter(scores.items()))
        why.append(f"{model} gives it {p * 100:.0f}% AI.")
    for d in sentence.get("diagnostics", []):
        why.append(f"{d['pattern'].replace('_', ' ')}: “{d['match']}” ({d['suggestion']}).")
    for t in tells_by_block.get(sentence["block"], []):
        if t["example"] and (t["example"].strip("…") in sentence["sentence"]
                             or sentence["sentence"] in t["example"]):
            why.append(f"{t['label']}.")
    if perplexity and perplexity["per_sentence"]:
        ppl = perplexity["by_index"].get(sentence["index"])
        mean = perplexity.get("mean")
        if ppl and mean:
            if ppl < mean * 0.5:
                why.append(f"Very predictable to GPT-2 (perplexity {ppl:.0f}, page mean {mean:.0f}).")
            elif ppl > mean * 2:
                why.append(f"Unusual to GPT-2 (perplexity {ppl:.0f}, page mean {mean:.0f}).")
    return why


def analyze(source, models=None, device=None, perplexity=False, tells=True,
            low_memory=False, progress=None):
    """Analyse a Loaded source (or raw text / a Document) and return the report."""
    if isinstance(source, Loaded):
        loaded = source
    elif isinstance(source, Document):
        loaded = Loaded(source, source.source, source.title or "document")
    else:
        loaded = Loaded(parse_text(source or ""), "text", "pasted text")
    document = loaded.document
    model_ids = REGISTRY.parse(models, DEFAULT_MODEL)

    rows, passages = _score_all(document, model_ids, device, low_memory, progress)
    if len(model_ids) == 1:
        report = build_report(document, rows, passages, model_ids[0])
        ensemble.annotate(report, rows, passages, model_ids)
    else:
        report = ensemble.build_ensemble_report(document, rows, passages, model_ids)
    report["models"] = model_ids
    report["source"] = {"kind": loaded.kind, "label": loaded.label, "title": document.title,
                        "has_screenshot": bool(loaded.screenshot)}
    report["model_info"] = {m: REGISTRY.resolve(m).public() for m in model_ids}

    if progress:
        progress({"stage": "tells"})
    structure = find_tells(document) if tells else {"tells": [], "summary": {}}
    visual = find_visual_tells(loaded.visual, document) if tells and loaded.visual else []
    for t in structure["tells"]:  # give structure tells a place on the screenshot too
        rects = [document.blocks[i].meta["rect"] for i in t["blocks"]
                 if i < len(document.blocks) and document.blocks[i].meta.get("rect")]
        if rects:
            t["rects"] = rects
    for n, t in enumerate(structure["tells"] + visual):
        t["n"] = n
    report["tells"] = {"structure": structure["tells"], "visual": visual,
                       "summary": structure["summary"],
                       "note": "Structure and style tells are a separate signal. They are "
                               "not part of any model score."}
    if loaded.visual:
        report["page"] = {k: loaded.visual.get(k) for k in ("page", "clipped_at")}

    report["perplexity"] = None
    if perplexity:
        if progress:
            progress({"stage": "perplexity"})
        from .perplexity import perplexity_report
        scored = [s for s in report["sentences"] if s["label"] != "Skipped"]
        ppl = perplexity_report([s["sentence"] for s in scored], device=device)
        ppl["by_index"] = {s["index"]: p for s, p in zip(scored, ppl["per_sentence"])}
        for s, p in zip(scored, ppl["per_sentence"]):
            s["perplexity"] = p
        report["perplexity"] = ppl

    tells_by_block = {}
    for t in structure["tells"]:
        for b in t["blocks"]:
            tells_by_block.setdefault(b, []).append(t)
    for s in report["sentences"]:
        if s["label"] != "Skipped":
            s["why"] = _explain(s, report, tells_by_block, report["perplexity"])
    if report["perplexity"]:
        report["perplexity"].pop("by_index", None)
    report["assessment"] = assess(report, len(model_ids))
    return report


def compare(report_a, report_b):
    """Before/after figures for two reports (a = before, b = after)."""
    def tell_total(r):
        t = r.get("tells") or {}
        return len(t.get("structure", [])) + len(t.get("visual", []))

    def patterns(r):
        return sum(r.get("pattern_totals", {}).values())

    def calibrated(r):
        return r.get("assessment", {}).get(
            "ai_pct", r.get("operating_point", {}).get("calibrated_document_pct",
                                                       r["document_ai_pct"]))

    def label(r):
        # The same words as the result page. A report with no assessment (built
        # by hand) falls back to the legacy reading of its document score.
        return r.get("assessment", {}).get("label") or verdict(r["document_ai_pct"])

    def flagged(r):
        return r.get("operating_point", {}).get("flagged_sentences", r["ai_count"])

    return {
        "verdicts": [label(report_a), label(report_b)],
        "calibrated_document_pct": [calibrated(report_a), calibrated(report_b)],
        "delta_calibrated_document_pct": round(calibrated(report_a) - calibrated(report_b), 1),
        "operating_point_flagged": [flagged(report_a), flagged(report_b)],
        # True where one model ran: that side's document_ai_pct, sentence_ai_pct
        # and flagged_sentences are on the model's raw scale.
        "raw_scale": [len(report_a.get("models", [])) == 1, len(report_b.get("models", [])) == 1],
        "delta_ai_pct": round(report_a["model_ai_pct"] - report_b["model_ai_pct"], 1),
        "delta_document_ai_pct": round(report_a["document_ai_pct"] - report_b["document_ai_pct"], 1),
        "sentence_ai_pct": [report_a["model_ai_pct"], report_b["model_ai_pct"]],
        "document_ai_pct": [report_a["document_ai_pct"], report_b["document_ai_pct"]],
        "flagged_sentences": [report_a["ai_count"], report_b["ai_count"]],
        "patterns": [patterns(report_a), patterns(report_b)],
        "tells": [tell_total(report_a), tell_total(report_b)],
    }


__all__ = ["Loaded", "analyze", "assess", "compare", "load_source", "read_text_file",
           "weighted_pct"]
