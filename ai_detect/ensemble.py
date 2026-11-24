"""Calibration and the multi-model ensemble.

Why raw probabilities are not averaged: the detectors put their scores on
different scales and none of them is calibrated for single sentences. At the
raw 0.5 cut-off every model here calls between 39% and 76% of human-written
sentences "AI" on the local evaluation corpus. So each model gets its own
operating point, fitted on human text:

    threshold  the logit margin that 5% of human items exceed
    scale      the robust spread of human margins

    calibrated = sigmoid((margin - threshold) / scale)

which puts every model's "5% of humans score above this" point at 0.5 and makes
one unit mean the same thing for each. The ensemble score is the mean of the
calibrated values; agreement is how many models are over their own threshold.

The numbers live in calibration.json, written by scripts/calibrate_ensemble.py.
They come from a small local corpus (see docs/MODEL-EVAL-2026-11.md). On that
corpus no combination beat the best single model; the ensemble is a cross-check
that shows where models disagree, not an accuracy upgrade.
"""

import json
from importlib import resources

from .backends import sigmoid
from .detector import build_report, weighted_pct

_FALLBACK = {"threshold": 0.0, "scale": 1.0}
_CALIBRATION = None


def calibration():
    global _CALIBRATION
    if _CALIBRATION is None:
        try:
            raw = resources.files("ai_detect").joinpath("calibration.json").read_text("utf-8")
            _CALIBRATION = json.loads(raw)
        except (OSError, ValueError):
            _CALIBRATION = {"models": {}, "method": "mean calibrated probability"}
    return _CALIBRATION


def operating_point(model_id, level="sentence"):
    """{threshold, scale} for a model at 'sentence' or 'passage' level. A model
    with no fitted calibration falls back to its raw scale (threshold 0)."""
    return calibration()["models"].get(model_id, {}).get(level, _FALLBACK)


def calibrated(model_id, margin, level="sentence"):
    point = operating_point(model_id, level)
    return sigmoid((margin - point["threshold"]) / point["scale"])


def combine(margins, level="sentence"):
    """Combine one item's per-model margins.

    Returns {score, calibrated: {model: p}, flags: {model: bool}, agreement, n}.
    """
    cal = {m: calibrated(m, x, level) for m, x in margins.items()}
    flags = {m: x > operating_point(m, level)["threshold"] for m, x in margins.items()}
    return {
        "score": sum(cal.values()) / len(cal) if cal else 0.0,
        "calibrated": {m: round(p, 4) for m, p in cal.items()},
        "flags": flags,
        "agreement": sum(flags.values()),
        "n": len(cal),
    }


def annotate(report, rows, passages, model_ids):
    """Add calibrated scores, per-model flags and agreement to a built report."""
    by_index = {r["index"]: r for r in rows if r["scoreable"]}
    flagged = 0
    for s in report["sentences"]:
        row = by_index.get(s["index"])
        if row is None:
            continue
        c = combine({m: row["margins"][m] for m in model_ids}, "sentence")
        s["calibrated"], s["flags"], s["agreement"] = c["calibrated"], c["flags"], c["agreement"]
        s["calibrated_prob"] = round(c["score"], 4)
        flagged += c["score"] >= 0.5
    for out, p in zip(report["passages"], passages):
        c = combine({m: p["margins"][m] for m in model_ids}, "passage")
        out["calibrated"], out["flags"], out["agreement"] = c["calibrated"], c["flags"], c["agreement"]
        out["calibrated_prob"] = round(c["score"], 4)
    cal = calibration()
    report["operating_point"] = {
        "target_fpr": cal.get("target_fpr", 0.05),
        "fitted": cal.get("fitted"),
        "flagged_sentences": flagged,
        "flagged_passages": sum(p["calibrated_prob"] >= 0.5 for p in report["passages"]),
        "calibrated_document_pct": weighted_pct(report["passages"], lambda p: p["calibrated_prob"]),
        "uncalibrated_models": [m for m in model_ids if m not in cal.get("models", {})],
        "note": "Calibrated to flag about 5% of human-written text on the local evaluation "
                "corpus. A flag is a prompt to look, not a finding.",
    }
    return report


def build_ensemble_report(document, rows, passages, model_ids):
    """The report for several models: ai_prob is the ensemble's calibrated mean."""
    def combined(item):
        level = "passage" if "words" in item else "sentence"
        return combine({m: item["margins"][m] for m in model_ids}, level)["score"]

    report = build_report(document, rows, passages, model_ids[0], prob_of=combined,
                          label="ensemble")
    per_model = {}
    for m in model_ids:
        single = [r["scores"][m] for r in rows if r["scoreable"]]
        per_model[m] = {
            "model_ai_pct": round(sum(single) / len(single) * 100, 1) if single else 0.0,
            "ai_count_raw": sum(p >= 0.5 for p in single),
            "document_ai_pct": weighted_pct(passages, lambda p, m=m: p["scores"][m]),
            "document_flag": None,
        }
    annotate(report, rows, passages, model_ids)
    for m in model_ids:
        per_model[m]["flagged_sentences"] = sum(
            1 for s in report["sentences"] if s.get("flags", {}).get(m))
        votes = [p["flags"][m] for p in report["passages"]]
        words = [p["words"] for p in report["passages"]]
        share = sum(w for w, v in zip(words, votes) if v) / (sum(words) or 1)
        per_model[m]["document_flag"] = share >= 0.5
    report["per_model"] = per_model
    report["ensemble"] = {
        "method": calibration().get("method", "mean calibrated probability"),
        "n": len(model_ids),
        "document_agreement": sum(1 for m in model_ids if per_model[m]["document_flag"]),
        "note": "ai_prob is the mean of each model's calibrated probability. 'scores' holds "
                "each model's raw probability; 'flags' says which models are over their own "
                "threshold.",
    }
    return report
