"""Compare ensemble combination methods and write ai_detect/calibration.json.

    python scripts/calibrate_ensemble.py docs/eval-data/results-2026-11-24-cpu.json

Reads the per-model logit margins that eval_models.py saved. For each of 200
random splits of the passages into two halves it fits each model's threshold
and scale on one half and scores every combination method on the other, so no
method is judged on data it was fitted to. Sentences travel with their passage.

Then it fits the calibration on ALL the data and writes it to the package.
"""

import json
import math
import os
import random
import statistics
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FPR = 0.05
SPLITS = 200


def quantile(values, q):
    s = sorted(values)
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def auroc(human, ai):
    return sum((a > h) + 0.5 * (a == h) for a in ai for h in human) / (len(ai) * len(human))


def tpr(human, ai):
    thr = quantile(human, 1 - FPR)
    return sum(a > thr for a in ai) / len(ai)


def sigmoid(x):
    return 1 / (1 + math.exp(-max(-40.0, min(40.0, x))))


def fit(human_margins):
    """Threshold = the margin 5% of human items exceed. Scale = spread of the
    human margins (IQR / 1.349, the robust stand-in for a standard deviation)."""
    iqr = quantile(human_margins, 0.75) - quantile(human_margins, 0.25)
    return {"threshold": quantile(human_margins, 1 - FPR), "scale": max(iqr / 1.349, 0.25)}


METHODS = {
    "mean raw probability": lambda ms, cal: statistics.fmean(sigmoid(m) for m in ms),
    "mean calibrated probability": lambda ms, cal: statistics.fmean(
        sigmoid((m - c["threshold"]) / c["scale"]) for m, c in zip(ms, cal)),
    "median calibrated probability": lambda ms, cal: statistics.median(
        sigmoid((m - c["threshold"]) / c["scale"]) for m, c in zip(ms, cal)),
    "vote share (models over threshold)": lambda ms, cal: statistics.fmean(
        m > c["threshold"] for m, c in zip(ms, cal)),
}


def main():
    path = sys.argv[1]
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    models = list(data["models"])
    corpus = data["corpus"]
    levels = {
        "sentence": (corpus["sentence_labels"], corpus["sentence_doc"], "sentence_margins"),
        "passage": (corpus["passage_labels"], list(range(len(corpus["passage_labels"]))),
                    "passage_margins"),
    }
    n_docs = len(corpus["passage_labels"])
    rng = random.Random(20261124)
    table = {level: {} for level in levels}
    for _ in range(SPLITS):
        docs = list(range(n_docs))
        rng.shuffle(docs)
        fit_docs = set(docs[: n_docs // 2])
        for level, (labels, doc_of, key) in levels.items():
            margins = {m: data["models"][m][key] for m in models}
            fit_idx = [i for i, d in enumerate(doc_of) if d in fit_docs]
            test_idx = [i for i, d in enumerate(doc_of) if d not in fit_docs]
            cal = [fit([margins[m][i] for i in fit_idx if labels[i] == "human"]) for m in models]
            scores = {name: [fn([margins[m][i] for m in models], cal) for i in test_idx]
                      for name, fn in METHODS.items()}
            for m in models:
                scores["single: " + m] = [margins[m][i] for i in test_idx]
            for name, values in scores.items():
                human = [v for v, i in zip(values, test_idx) if labels[i] == "human"]
                ai = [v for v, i in zip(values, test_idx) if labels[i] == "ai"]
                if len(human) < 5 or len(ai) < 5:
                    continue
                table[level].setdefault(name, []).append((auroc(human, ai), tpr(human, ai)))

    summary = {}
    for level, rows in table.items():
        print(f"\n{level} level, mean over {SPLITS} held-out halves")
        print(f"  {'method':40} AUROC   TPR@5%FPR")
        summary[level] = {}
        for name, vals in sorted(rows.items(), key=lambda kv: -statistics.fmean(v[0] for v in kv[1])):
            a = statistics.fmean(v[0] for v in vals)
            t = statistics.fmean(v[1] for v in vals)
            summary[level][name] = {"auroc": round(a, 4), "tpr_at_5pct_fpr": round(t, 4)}
            print(f"  {name:40} {a:.4f}  {t:.4f}")

    calibration = {
        "_about": "Per-model operating points fitted by scripts/calibrate_ensemble.py on the "
                  "local evaluation corpus. threshold = logit margin exceeded by 5% of human "
                  "items; scale = robust spread of human margins. See docs/MODEL-EVAL-2026-11.md.",
        "fitted": data["date"], "device": data["device"], "target_fpr": FPR,
        "corpus": {k: corpus[k] for k in ("passages", "sentences", "human_passages", "ai_passages")},
        "method": "mean calibrated probability",
        "models": {},
        "held_out_comparison": summary,
    }
    for m in models:
        entry = {}
        for level, (labels, _doc_of, key) in levels.items():
            human = [x for x, lab in zip(data["models"][m][key], labels) if lab == "human"]
            f_ = fit(human)
            entry[level] = {"threshold": round(f_["threshold"], 3), "scale": round(f_["scale"], 3)}
        calibration["models"][m] = entry
    out = os.path.join(ROOT, "ai_detect", "calibration.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(calibration, f, indent=1)
    print("\nwrote", os.path.relpath(out, ROOT))
    for m, e in calibration["models"].items():
        print(f"  {m:14} sentence thr {e['sentence']['threshold']:7.2f} scale {e['sentence']['scale']:5.2f}"
              f" | passage thr {e['passage']['threshold']:7.2f} scale {e['passage']['scale']:5.2f}")


if __name__ == "__main__":
    main()
