"""
Detection backends and the orchestration layer.

Two backends share one interface (`score(sentences) -> list[float]`, each a
0..1 probability that the sentence is AI-written):

  * DesklibBackend  — desklib/ai-text-detector-v1.01 (DeBERTa-v3-large) via
                      transformers + torch. Most accurate; ~1.7 GB one-time
                      download; CPU by default, CUDA if available.
  * LightBackend    — onnx-community/tmr-ai-text-detector-ONNX (RoBERTa-base,
                      int8) via onnxruntime. ~126 MB; faster to fetch; can use
                      DirectML / CUDA execution providers when installed.

`classify_text()` splits text into sentences, scores the long ones, attaches
pattern diagnostics, and returns an aggregate report.
"""

import os
import sys
import threading

from .patterns import (
    calculate_sdsl,
    count_pattern_totals,
    diagnose_sentence,
    sent_tokenize,
)

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

DESKLIB_MODEL = "desklib/ai-text-detector-v1.01"
LIGHT_REPO = "onnx-community/tmr-ai-text-detector-ONNX"
LIGHT_ONNX_FILE = "onnx/model_int8.onnx"

MODELS = {
    "desklib": {
        "backend": "desklib",
        "repo": DESKLIB_MODEL,
        "label": "desklib/ai-text-detector-v1.01 (DeBERTa-v3-large)",
        "approx_mb": 1736,
        # Representative large file — present only once the model is fully fetched.
        "cache_probe": "model.safetensors",
    },
    "light": {
        "backend": "light",
        "repo": LIGHT_REPO,
        "onnx_file": LIGHT_ONNX_FILE,
        "label": "tmr-ai-text-detector int8 (RoBERTa-base, ONNX)",
        "approx_mb": 126,
        "cache_probe": LIGHT_ONNX_FILE,
    },
}
DEFAULT_MODEL = "desklib"

BATCH_SIZE = 8
MIN_WORDS = 5  # Sentences below this are skipped (headers/fragments — too short to score reliably)


def verdict(pct):
    """Map an overall AI percentage to a plain-English verdict (single source of truth)."""
    return "LIKELY AI" if pct > 50 else "LIKELY HUMAN" if pct < 40 else "MIXED"


# ---------------------------------------------------------------------------
# Device resolution (torch)
# ---------------------------------------------------------------------------

def resolve_torch_device(pref=None):
    """Pick a torch device. pref: 'auto' | 'cpu' | 'cuda' (or None -> env/auto).

    Honours the AI_DETECT_DEVICE env var when pref is not given. Default is
    'auto' = CUDA if a GPU is present, otherwise CPU ("CPU unless a GPU is
    installed").
    """
    import torch

    pref = (pref or os.environ.get("AI_DETECT_DEVICE") or "auto").lower()
    if pref == "cpu":
        return torch.device("cpu")
    if pref in ("cuda", "gpu"):
        if torch.cuda.is_available():
            return torch.device("cuda")
        print("Requested GPU but no CUDA device is available — falling back to CPU.",
              file=sys.stderr)
        return torch.device("cpu")
    # auto
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def preload_dependencies():
    """Import the heavy backend libraries in the calling (ideally main) thread.

    Importing numpy / onnxruntime / torch / transformers for the FIRST time from
    inside a running MCP stdio server — whether in the event-loop thread or a
    worker thread it dispatches to — can deadlock on the import machinery. Calling
    this once at server startup, before mcp.run(), makes every later import a cheap
    sys.modules cache hit, so model loads during a request no longer hang. Missing
    optional deps (e.g. onnxruntime when 'light' isn't installed) are ignored.
    """
    import importlib
    for mod in ("numpy", "torch", "onnxruntime", "huggingface_hub"):
        try:
            importlib.import_module(mod)
        except Exception:
            pass
    # transformers lazy-loads its submodules; touch the exact classes the backends
    # use so those submodules import now rather than mid-request.
    try:
        from transformers import (  # noqa: F401
            AutoConfig, AutoModel, AutoTokenizer, PreTrainedModel,
        )
    except Exception:
        pass


def _announce_download(cfg):
    """Warn on stderr the first time a model is fetched, so a long download is not mysterious."""
    print(
        f"First run with '{cfg['label']}': downloading ~{cfg['approx_mb']} MB "
        f"from Hugging Face (cached in ~/.cache/huggingface for next time)...",
        file=sys.stderr,
    )


def prefetch_model(model_name=DEFAULT_MODEL):
    """Download a model's files into the local HF cache WITHOUT loading it onto a device.

    Lets a background startup warmup make the first detect call fast (no ~1.7 GB
    wait) while leaving GPU/RAM untouched until detection actually runs — the
    weights land on disk; the tensors aren't materialised here (so this never
    contends with other GPU work). No-op if the model is already cached. Never
    raises: on a network/hub error it logs and returns False, and the first detect
    call falls back to downloading the normal way.
    """
    cfg = MODELS.get(model_name)
    if not cfg:
        return False
    if is_model_cached(model_name):
        return True
    try:
        from huggingface_hub import snapshot_download
    except Exception:
        return False
    # Weights + config + tokenizer only. '*.safetensors' avoids pulling a
    # duplicate fp32 '.bin' when a repo ships both; the light model needs just its
    # one ONNX file.
    patterns = ["*.json", "*.txt", "tokenizer*", "*.model", "*.spm",
                "vocab*", "merges*", "special_tokens*"]
    patterns.append(cfg["onnx_file"] if cfg["backend"] == "light" else "*.safetensors")
    _announce_download(cfg)
    try:
        snapshot_download(cfg["repo"], allow_patterns=patterns)
    except Exception as e:  # network, auth, hub outage — stay non-fatal
        print(f"ai-detect: background model prefetch failed ({e}); the first "
              "detect call will download it instead.", file=sys.stderr)
        return False
    return is_model_cached(model_name)


# ---------------------------------------------------------------------------
# desklib backend (transformers + torch)
# ---------------------------------------------------------------------------

class DesklibBackend:
    """DeBERTa-v3-large detector with a custom mean-pooled sigmoid head."""

    name = "desklib"

    def __init__(self, device=None):
        import torch
        import torch.nn as nn
        from transformers import AutoConfig, AutoModel, AutoTokenizer, PreTrainedModel

        cfg = MODELS["desklib"]
        self._torch = torch
        # One inference at a time per loaded model: the MCP server can run several
        # detections concurrently, and a single device serialises the work anyway —
        # sharing it without a lock just risks overlapping batches on one GPU.
        self._lock = threading.Lock()

        class DesklibAIDetectionModel(PreTrainedModel):
            config_class = AutoConfig
            all_tied_weights_keys = {}

            def __init__(self, config):
                super().__init__(config)
                self.model = AutoModel.from_config(config)
                self.classifier = nn.Linear(config.hidden_size, 1)
                self.init_weights()

            def forward(self, input_ids, attention_mask=None, labels=None):
                outputs = self.model(input_ids, attention_mask=attention_mask)
                last_hidden_state = outputs[0]
                mask = attention_mask.unsqueeze(-1).expand(
                    last_hidden_state.size()).to(last_hidden_state.dtype)
                sum_embeddings = torch.sum(last_hidden_state * mask, dim=1)
                sum_mask = torch.clamp(mask.sum(dim=1), min=1e-9)
                pooled = sum_embeddings / sum_mask
                return {"logits": self.classifier(pooled)}

        self.device = resolve_torch_device(device)
        if not is_model_cached("desklib"):
            _announce_download(cfg)
        print("Loading model...", file=sys.stderr)
        self.tokenizer = AutoTokenizer.from_pretrained(cfg["repo"])
        dtype = torch.float32
        if self.device.type == "cuda" and torch.cuda.is_bf16_supported():
            dtype = torch.bfloat16
        self.model = DesklibAIDetectionModel.from_pretrained(cfg["repo"], dtype=dtype)
        self.model.to(self.device).eval()
        print(f"Model loaded on {self.device} ({cfg['label']})", file=sys.stderr)

    def score(self, sentences):
        torch = self._torch
        probs = []
        with self._lock:
            for start in range(0, len(sentences), BATCH_SIZE):
                batch = sentences[start:start + BATCH_SIZE]
                enc = self.tokenizer(
                    batch, padding=True, truncation=True, max_length=512,
                    return_tensors="pt",
                ).to(self.device)
                with torch.inference_mode():
                    logits = self.model(
                        input_ids=enc["input_ids"],
                        attention_mask=enc["attention_mask"],
                    )["logits"]
                    batch_probs = torch.sigmoid(logits).squeeze(-1).tolist()
                if isinstance(batch_probs, float):
                    batch_probs = [batch_probs]
                probs.extend(batch_probs)
        return probs


# ---------------------------------------------------------------------------
# light backend (onnxruntime)
# ---------------------------------------------------------------------------

class LightBackend:
    """Quantised RoBERTa detector run through onnxruntime (id2label 0=human, 1=ai)."""

    name = "light"

    def __init__(self, device=None):
        import numpy as np
        import onnxruntime as ort
        from huggingface_hub import hf_hub_download
        from transformers import AutoTokenizer

        cfg = MODELS["light"]
        self._np = np
        self._lock = threading.Lock()  # see DesklibBackend

        if not is_model_cached("light"):
            _announce_download(cfg)
        print("Loading light model (ONNX)...", file=sys.stderr)
        self.tokenizer = AutoTokenizer.from_pretrained(cfg["repo"])
        onnx_path = hf_hub_download(cfg["repo"], filename=cfg["onnx_file"])

        providers = _onnx_providers(ort, device)
        self.session = ort.InferenceSession(onnx_path, providers=providers)
        self.input_names = {i.name for i in self.session.get_inputs()}
        print(
            f"Model loaded via onnxruntime {self.session.get_providers()[0]} "
            f"({cfg['label']})",
            file=sys.stderr,
        )

    def score(self, sentences):
        np = self._np
        probs = []
        with self._lock:
            for start in range(0, len(sentences), BATCH_SIZE):
                batch = sentences[start:start + BATCH_SIZE]
                enc = self.tokenizer(
                    batch, padding=True, truncation=True, max_length=512,
                    return_tensors="np",
                )
                feeds = {}
                for name in ("input_ids", "attention_mask", "token_type_ids"):
                    if name in self.input_names and name in enc:
                        feeds[name] = enc[name].astype(np.int64)
                if "token_type_ids" in self.input_names and "token_type_ids" not in feeds:
                    feeds["token_type_ids"] = np.zeros_like(feeds["input_ids"])
                logits = self.session.run(None, feeds)[0]
                # softmax over the 2 classes, take P(class 1 = ai)
                m = logits.max(axis=1, keepdims=True)
                exp = np.exp(logits - m)
                softmax = exp / exp.sum(axis=1, keepdims=True)
                probs.extend(softmax[:, 1].tolist())
        return probs


def _onnx_providers(ort, device):
    """Prefer a GPU execution provider when installed and requested; else CPU."""
    available = ort.get_available_providers()
    pref = (device or os.environ.get("AI_DETECT_DEVICE") or "auto").lower()
    gpu_order = ["DmlExecutionProvider", "CUDAExecutionProvider", "ROCMExecutionProvider"]
    if pref == "cpu":
        return ["CPUExecutionProvider"]
    chosen = [p for p in gpu_order if p in available]
    if pref in ("cuda", "gpu") and not chosen:
        print("Requested GPU but no GPU execution provider is installed "
              "(try: pip install onnxruntime-directml) — using CPU.", file=sys.stderr)
    return chosen + ["CPUExecutionProvider"]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def is_model_cached(model_name):
    """Whether a model's weights are already in the local HF cache.

    Cheap: probes a single representative large file (desklib's safetensors,
    the light model's ONNX) rather than walking the whole cache. Returns False
    for unknown models or if huggingface_hub can't answer.
    """
    cfg = MODELS.get(model_name)
    if not cfg:
        return False
    probe = cfg.get("cache_probe") or "config.json"
    try:
        from huggingface_hub import try_to_load_from_cache
        return isinstance(try_to_load_from_cache(cfg["repo"], probe), str)
    except Exception:
        return False


_DETECTOR_CACHE = {}
# Guards construction only. The MCP server runs detections in worker threads, so
# two concurrent first calls for the same model would otherwise both miss the cache
# and each load a ~1.7 GB copy onto the device — doubling VRAM for no reason, or
# OOMing outright. A per-key lock lets a second model load in parallel with the
# first; only same-key callers queue.
_DETECTOR_LOCKS = {}
_DETECTOR_LOCKS_GUARD = threading.Lock()


def _device_key(device):
    """Normalise a device intent so equivalent forms share one cache entry.

    None / unset env / '' all collapse to 'auto', and 'gpu' aliases to 'cuda',
    so a caller can't load the same model twice for the same device.
    """
    d = (device or os.environ.get("AI_DETECT_DEVICE") or "auto").strip().lower()
    return "cuda" if d == "gpu" else d


def get_detector(model=DEFAULT_MODEL, device=None):
    """Return a cached backend for the given model name ('desklib' or 'light')."""
    if model not in MODELS:
        raise ValueError(f"Unknown model '{model}'. Choose from: {', '.join(MODELS)}")
    key = (model, _device_key(device))

    cached = _DETECTOR_CACHE.get(key)  # fast path: no lock once loaded
    if cached is not None:
        return cached

    with _DETECTOR_LOCKS_GUARD:
        lock = _DETECTOR_LOCKS.setdefault(key, threading.Lock())
    with lock:
        if key not in _DETECTOR_CACHE:  # re-check: another thread may have won
            backend = MODELS[model]["backend"]
            if backend == "desklib":
                _DETECTOR_CACHE[key] = DesklibBackend(device=device)
            elif backend == "light":
                _DETECTOR_CACHE[key] = LightBackend(device=device)
            else:  # pragma: no cover - registry guard
                raise ValueError(f"Unknown backend '{backend}'")
    return _DETECTOR_CACHE[key]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def classify_text(text, model=DEFAULT_MODEL, device=None, detector=None):
    """Classify each sentence and return an aggregate report.

    Returns a dict with per-sentence results (label, probabilities, diagnostics),
    the overall model AI %, counts, SDSL text metrics, and pattern totals.
    """
    if detector is None:
        detector = get_detector(model=model, device=device)

    sentences = sent_tokenize(text)
    if not sentences:
        return {
            "sentences": [], "model_ai_pct": 0.0, "ai_count": 0, "human_count": 0,
            "skipped_count": 0, "total": 0, "model": getattr(detector, "name", model),
            "text_metrics": calculate_sdsl([]), "pattern_totals": {},
        }

    results = [None] * len(sentences)
    scoreable, scoreable_indices = [], []
    for i, s in enumerate(sentences):
        if len(s.split()) < MIN_WORDS:
            results[i] = {
                "sentence": s, "label": "Skipped", "confidence": 0.0,
                "ai_prob": 0.0, "human_prob": 0.0, "diagnostics": [],
            }
        else:
            scoreable.append(s)
            scoreable_indices.append(i)

    ai_count = 0
    all_probs = []
    if scoreable:
        probs = detector.score(scoreable)
        for s, ai_prob, idx in zip(scoreable, probs, scoreable_indices):
            ai_prob = float(ai_prob)
            human_prob = 1.0 - ai_prob
            label = "AI" if ai_prob >= 0.5 else "Human"
            if label == "AI":
                ai_count += 1
            all_probs.append(ai_prob)
            results[idx] = {
                "sentence": s,
                "label": label,
                "confidence": round(max(ai_prob, human_prob), 4),
                "ai_prob": round(ai_prob, 4),
                "human_prob": round(human_prob, 4),
                "diagnostics": diagnose_sentence(s),
            }

    model_ai_pct = round(sum(all_probs) / len(all_probs) * 100, 1) if all_probs else 0.0
    return {
        "sentences": results,
        "model_ai_pct": model_ai_pct,
        "ai_count": ai_count,
        "human_count": len(scoreable) - ai_count,
        "skipped_count": len(sentences) - len(scoreable),
        "total": len(sentences),
        "model": getattr(detector, "name", model),
        "text_metrics": calculate_sdsl(scoreable),
        "pattern_totals": count_pattern_totals(results),
    }
