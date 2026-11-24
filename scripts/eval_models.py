"""Evaluate every registered detector on this machine.

    python scripts/eval_models.py fetch              # human texts -> eval_cache/
    python scripts/eval_models.py generate           # AI texts from a local LLM
    python scripts/eval_models.py run [--models a,b] # score, time, calibrate

Nothing fetched or generated is committed: the human texts are other people's
writing (Wikipedia CC BY-SA, Project Gutenberg public domain, essays under
their authors' copyright) and are only read locally to measure the models. The
committed outputs are scores, in docs/eval-data/.

The corpus is small (a few dozen passages, a few hundred sentences) and the AI
half comes from ONE local generator. It is enough to compare models against
each other on this machine and to set rough per-model thresholds. It is not a
benchmark; RAID is.
"""

import argparse
import html
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
CACHE = os.path.join(ROOT, "eval_cache")
OUT = os.path.join(ROOT, "docs", "eval-data")
UA = {"User-Agent": "ai-detect-eval/2.0 (local model evaluation script)"}

WIKI = ["Tide", "Bread", "Steam engine", "Honey bee", "Printing press", "Glacier",
        "Lighthouse", "Violin", "Photosynthesis", "Roman roads", "Coffee", "Typewriter"]
GUTENBERG = {  # id: (label, register)
    1342: "Pride and Prejudice (Austen, 1813)", 2009: "On the Origin of Species (Darwin, 1859)",
    74: "The Adventures of Tom Sawyer (Twain, 1876)",
    5827: "The Problems of Philosophy (Russell, 1912)",
    1661: "The Adventures of Sherlock Holmes (Doyle, 1892)",
    2701: "Moby-Dick (Melville, 1851)",
}
ESSAYS = {  # personal essays published well before 2022
    "https://paulgraham.com/avg.html": "Beating the Averages (2001)",
    "https://paulgraham.com/makersschedule.html": "Maker's Schedule, Manager's Schedule (2009)",
    "https://paulgraham.com/procrastination.html": "Good and Bad Procrastination (2005)",
    "https://paulgraham.com/love.html": "How to Do What You Love (2006)",
    "https://paulgraham.com/startupideas.html": "How to Get Startup Ideas (2012)",
    "https://paulgraham.com/essay.html": "The Age of the Essay (2004)",
}
AI_PROMPTS = (
    [("encyclopedic", f"Write a 220-word encyclopedia-style overview of: {t}.") for t in WIKI]
    + [("essay", f"Write a 220-word personal essay passage, first person, about: {t}.") for t in (
        "why a small team can beat a big company", "how meetings break up a working day",
        "putting off small tasks to do important work", "choosing work you enjoy",
        "where good business ideas come from", "why school essays are dull")]
    + [("fiction", f"Write a 220-word passage of narrative fiction: {t}.") for t in (
        "a proud man meets a sharp-witted woman at a country dance",
        "a boy tricks his friends into doing his chore", "a detective reads a visitor's past from his hands",
        "a sailor describes the first sight of a whale", "a naturalist watches finches on an island",
        "a philosopher looks at a table and doubts it")]
    + [("blog", f"Write a 220-word first-person blog post section about: {t}.") for t in (
        "three months with a new coffee grinder", "switching sim racing wheelbases",
        "setting up a home server", "a budget mechanical keyboard",
        "running a local language model on a gaming PC", "fixing a slow WordPress site")]
)


def _get(url):
    time.sleep(1.5)  # be a polite client
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
        return r.read().decode("utf-8", errors="replace")


def _gutenberg(book):
    """Plain text of a Project Gutenberg book, from the pglaf.org mirror
    (gutenberg.org itself turns scripted requests away)."""
    digits = str(book)
    folder = "/".join(digits[:-1]) or "0"
    for name in (f"{digits}-0.txt", f"{digits}.txt", f"{digits}-8.txt"):
        try:
            return _get(f"https://gutenberg.pglaf.org/{folder}/{digits}/{name}")
        except urllib.error.HTTPError:
            continue
    raise RuntimeError(f"Gutenberg book {book} not found on the mirror")


def _first_words(text, n=220):
    """The first ~n words, cut at a sentence end."""
    out, count = [], 0
    for sentence in re.split(r"(?<=[.!?])\s+", " ".join(text.split())):
        out.append(sentence)
        count += len(sentence.split())
        if count >= n:
            break
    return " ".join(out)


def _save(name, items):
    os.makedirs(CACHE, exist_ok=True)
    with open(os.path.join(CACHE, name), "w", encoding="utf-8") as f:
        json.dump(items, f, indent=1, ensure_ascii=False)
    print(f"saved {len(items)} items to eval_cache/{name}")


def cmd_fetch(_args):
    items = []
    url = ("https://en.wikipedia.org/w/api.php?action=query&prop=extracts&explaintext=1"
           "&exintro=1&exlimit=max&format=json&redirects=1&titles="
           + urllib.parse.quote("|".join(WIKI)))
    for page in json.loads(_get(url))["query"]["pages"].values():
        title = page["title"]
        items.append({"id": "wiki:" + title, "register": "encyclopedic", "label": "human",
                      "source": "https://en.wikipedia.org/wiki/" + title.replace(" ", "_"),
                      "text": _first_words(page.get("extract", ""))})
    for book, label in GUTENBERG.items():
        raw = _gutenberg(book)
        body = raw[len(raw) * 2 // 5:]
        paras = [p for p in re.split(r"\r?\n\s*\r?\n", body) if len(p.split()) > 60]
        items.append({"id": f"gutenberg:{book}", "register": "book", "label": "human",
                      "source": f"https://www.gutenberg.org/ebooks/{book}", "title": label,
                      "text": _first_words(" ".join(paras[1:5]))})
    for url, label in ESSAYS.items():
        page = _get(url)
        body = re.sub(r"(?is)<(script|style).*?</\1>", " ", page)
        body = html.unescape(re.sub(r"<[^>]+>", " ", re.sub(r"(?i)<br\s*/?>", "\n", body)))
        paras = [p for p in re.split(r"\n\s*\n", body) if len(p.split()) > 40]
        items.append({"id": "essay:" + url.rsplit("/", 1)[-1], "register": "essay",
                      "label": "human", "source": url, "title": label,
                      "text": _first_words(" ".join(paras[1:5]))})
    with open(os.path.join(ROOT, "examples", "human-sample.txt"), encoding="utf-8") as f:
        items.append({"id": "example:human-sample", "register": "blog", "label": "human",
                      "source": "examples/human-sample.txt", "text": f.read().strip()})
    _save("human.json", items)


def cmd_generate(args):
    items = []
    for i, (register, prompt) in enumerate(AI_PROMPTS):
        body = {"model": args.gen_model, "max_tokens": 600,
                "messages": [{"role": "user", "content": prompt + " Plain prose only: no "
                              "title, no headings, no lists, no preamble."}],
                "chat_template_kwargs": {"enable_thinking": False}}
        req = urllib.request.Request(args.endpoint.rstrip("/") + "/chat/completions",
                                     data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=300) as r:
            text = json.loads(r.read())["choices"][0]["message"]["content"].strip()
        items.append({"id": f"ai:{i:02d}", "register": register, "label": "ai",
                      "source": f"generated locally by {args.gen_model}", "prompt": prompt,
                      "text": text})
        print(i, register, len(text.split()), "words", flush=True)
    with open(os.path.join(ROOT, "examples", "ai-sample.txt"), encoding="utf-8") as f:
        items.append({"id": "example:ai-sample", "register": "blog", "label": "ai",
                      "source": "examples/ai-sample.txt", "text": f.read().strip()})
    _save("ai.json", items)


# ---------------------------------------------------------------------------
# Metrics (stdlib only)
# ---------------------------------------------------------------------------

def auroc(human, ai):
    """Probability a random AI item outscores a random human item."""
    if not human or not ai:
        return None
    wins = sum((a > h) + 0.5 * (a == h) for a in ai for h in human)
    return wins / (len(ai) * len(human))


def quantile(values, q):
    s = sorted(values)
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def tpr_at_fpr(human, ai, fpr=0.05):
    thr = quantile(human, 1 - fpr)
    return sum(a > thr for a in ai) / len(ai), thr


def summarise(human, ai):
    tpr, thr = tpr_at_fpr(human, ai)
    return {
        "n_human": len(human), "n_ai": len(ai),
        "auroc": round(auroc(human, ai), 4),
        "tpr_at_5pct_fpr": round(tpr, 4),
        "threshold_margin_5pct_fpr": round(thr, 3),
        "human_flagged_at_0": round(sum(h > 0 for h in human) / len(human), 4),
        "ai_flagged_at_0": round(sum(a > 0 for a in ai) / len(ai), 4),
        "human_median": round(quantile(human, 0.5), 3),
        "ai_median": round(quantile(ai, 0.5), 3),
        "human_iqr": round(quantile(human, 0.75) - quantile(human, 0.25), 3),
    }


def cmd_run(args):
    from ai_detect.detector import MIN_WORDS, get_detector, is_model_cached, unload_detector
    from ai_detect.models import MODELS
    from ai_detect.text import split_sentences

    docs = []
    for name in ("human.json", "ai.json"):
        with open(os.path.join(CACHE, name), encoding="utf-8") as f:
            docs.extend(json.load(f))
    with open(os.path.join(OUT, "pairs.json"), encoding="utf-8") as f:
        pairs = json.load(f)["pairs"]

    sentences = []  # (doc index, label, text)
    for di, d in enumerate(docs):
        for s in split_sentences(d["text"]):
            if len(s.split()) >= MIN_WORDS:
                sentences.append((di, d["label"], s))
    print(f"{len(docs)} passages, {len(sentences)} sentences, {len(pairs)} pairs", flush=True)

    model_ids = args.models.split(",") if args.models else list(MODELS)
    results = {"date": time.strftime("%Y-%m-%d"), "device": args.device,
               "corpus": {"passages": len(docs), "sentences": len(sentences),
                          "human_passages": sum(d["label"] == "human" for d in docs),
                          "ai_passages": sum(d["label"] == "ai" for d in docs),
                          "passage_ids": [d["id"] for d in docs],
                          "passage_labels": [d["label"] for d in docs],
                          "sentence_doc": [s[0] for s in sentences]},
               "models": {}}
    for mid in model_ids:
        cached = is_model_cached(mid)
        t0 = time.perf_counter()
        det = get_detector(mid, device=args.device)
        load_s = time.perf_counter() - t0
        det.margins(["A short warm-up sentence to settle the runtime."])
        t0 = time.perf_counter()
        sent_m = det.margins([s[2] for s in sentences])
        sent_s = time.perf_counter() - t0
        t0 = time.perf_counter()
        doc_m = det.margins([d["text"] for d in docs])
        doc_s = time.perf_counter() - t0
        pair_m = det.margins([p["formal"] for p in pairs] + [p["casual"] for p in pairs])
        n = len(pairs)
        human_s = [m for m, s in zip(sent_m, sentences) if s[1] == "human"]
        ai_s = [m for m, s in zip(sent_m, sentences) if s[1] == "ai"]
        human_d = [m for m, d in zip(doc_m, docs) if d["label"] == "human"]
        ai_d = [m for m, d in zip(doc_m, docs) if d["label"] == "ai"]
        results["models"][mid] = {
            "device": det.device_label, "was_cached": cached,
            "load_seconds": round(load_s, 2),
            "ms_per_sentence": round(sent_s / len(sentences) * 1000, 1),
            "ms_per_passage": round(doc_s / len(docs) * 1000, 1),
            "sentence": summarise(human_s, ai_s),
            "passage": summarise(human_d, ai_d),
            "pairs": {
                "formal_above_casual": sum(pair_m[i] > pair_m[n + i] for i in range(n)),
                "n": n,
                "formal_flagged_at_0": sum(m > 0 for m in pair_m[:n]),
                "casual_flagged_at_0": sum(m > 0 for m in pair_m[n:]),
                "formal_margins": [round(m, 2) for m in pair_m[:n]],
                "casual_margins": [round(m, 2) for m in pair_m[n:]],
            },
            "sentence_margins": [round(m, 3) for m in sent_m],
            "passage_margins": [round(m, 3) for m in doc_m],
        }
        r = results["models"][mid]
        print(mid, "load", r["load_seconds"], "s |", r["ms_per_sentence"], "ms/sent |",
              "sent AUROC", r["sentence"]["auroc"], "TPR@5", r["sentence"]["tpr_at_5pct_fpr"],
              "| passage AUROC", r["passage"]["auroc"], "TPR@5", r["passage"]["tpr_at_5pct_fpr"],
              "| pairs", r["pairs"]["formal_above_casual"], "/", n, flush=True)
        unload_detector(mid, device=args.device)
        del det
    results["corpus"]["sentence_labels"] = [s[1] for s in sentences]
    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, f"results-{results['date']}-{args.device}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=1)
    print("wrote", os.path.relpath(path, ROOT))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("fetch").set_defaults(fn=cmd_fetch)
    g = sub.add_parser("generate")
    g.add_argument("--endpoint", default="http://127.0.0.1:8000/v1")
    g.add_argument("--gen-model", default="friend-70b")
    g.set_defaults(fn=cmd_generate)
    r = sub.add_parser("run")
    r.add_argument("--models", default="")
    r.add_argument("--device", default="cpu", choices=["cpu", "cuda", "auto"])
    r.set_defaults(fn=cmd_run)
    args = ap.parse_args()
    random.seed(0)
    args.fn(args)


if __name__ == "__main__":
    main()
