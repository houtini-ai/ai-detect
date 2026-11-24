"""Perplexity and burstiness from a small local language model (opt-in).

This is a different kind of signal from the classifiers. A classifier was
trained to tell human from machine text. Perplexity only measures how
predictable each sentence is to one small language model (GPT-2, 2019):
low = the model saw it coming, high = it did not. Burstiness is how much that
figure varies from sentence to sentence.

It is reported as a readout with no verdict. Predictable text is not proof of
anything: plain instructions, legal boilerplate and well-edited prose all score
low. It is never blended into a model score.

Model: openai-community/gpt2, MIT, 137M parameters, 548 MB
(https://huggingface.co/openai-community/gpt2, read 24 Nov 2026).
"""

import math
import statistics
import threading

from .backends import _log, resolve_torch_device

PERPLEXITY_MODEL = "openai-community/gpt2"
PERPLEXITY_MB = 548
MAX_TOKENS = 512
_LOCK = threading.Lock()
_CACHE = {}


class PerplexityScorer:
    def __init__(self, device=None):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self._torch = torch
        self.device = resolve_torch_device(device)
        _log(f"Loading {PERPLEXITY_MODEL} for perplexity (~{PERPLEXITY_MB} MB on first run)...")
        self.tokenizer = AutoTokenizer.from_pretrained(PERPLEXITY_MODEL)
        self.model = AutoModelForCausalLM.from_pretrained(PERPLEXITY_MODEL)
        self.model.to(self.device).eval()
        self._bos = self.tokenizer.bos_token_id

    def nll(self, text):
        """(total negative log-likelihood in nats, token count) for one text,
        each token conditioned on the ones before it."""
        torch = self._torch
        ids = [self._bos] + self.tokenizer.encode(text)[:MAX_TOKENS - 1]
        if len(ids) < 2:
            return 0.0, 0
        x = torch.tensor([ids], device=self.device)
        with torch.inference_mode():
            logits = self.model(x).logits[0, :-1].float()
        logp = torch.log_softmax(logits, dim=-1)
        picked = logp[torch.arange(len(ids) - 1, device=self.device), x[0, 1:]]
        return float(-picked.sum()), len(ids) - 1


def get_scorer(device=None):
    key = str(device or "auto")
    with _LOCK:
        if key not in _CACHE:
            _CACHE[key] = PerplexityScorer(device)
        return _CACHE[key]


def perplexity_report(sentences, device=None, scorer=None):
    """Per-sentence and whole-text perplexity plus burstiness.

    sentences: list of strings (already split). Returns
    ``{model, per_sentence: [float|None], document, burstiness, mean, note}``.
    """
    scorer = scorer or get_scorer(device)
    per, total_nll, total_tokens = [], 0.0, 0
    for s in sentences:
        nll, n = scorer.nll(s)
        if n < 3:
            per.append(None)
            continue
        per.append(round(math.exp(min(nll / n, 20.0)), 1))
        total_nll += nll
        total_tokens += n
    scored = [p for p in per if p is not None]
    return {
        "model": PERPLEXITY_MODEL,
        "per_sentence": per,
        "document": round(math.exp(min(total_nll / total_tokens, 20.0)), 1) if total_tokens else None,
        "mean": round(statistics.fmean(scored), 1) if scored else None,
        "burstiness": round(statistics.pstdev(scored), 1) if len(scored) > 1 else None,
        "burstiness_cv": (round(statistics.pstdev(scored) / statistics.fmean(scored), 2)
                          if len(scored) > 1 else None),
        "sentences_scored": len(scored),
        "note": ("GPT-2 perplexity: how predictable each sentence is to a small 2019 "
                 "language model. Lower is more predictable. Burstiness is the spread "
                 "across sentences. A readout, not a verdict."),
    }
