"""Detection backends: one class per way of loading a model.

Every backend takes a ModelSpec and exposes the same two methods:

    margins(texts) -> list[float]   logit(AI) - logit(human), unbounded
    score(texts)   -> list[float]   sigmoid(margin): P(AI) in 0..1

``score`` is the contract the rest of the package relies on. ``margins`` is the
same information before squashing; the ensemble calibrates in that space.

Heavy libraries (torch, transformers, onnxruntime) are imported inside the
constructors, never at module import, so importing ai_detect stays cheap and
the CLI can print --help without loading PyTorch.
"""

import math
import os
import sys
import threading

from .normalize import normalizer

BATCH_SIZE = 8
MAX_TOKENS = 512


class MissingRuntimeError(RuntimeError):
    """A model needs an optional library that is not installed."""


def _import(module, spec):
    import importlib
    try:
        return importlib.import_module(module)
    except ImportError as e:
        how = (f"From the ai-detect folder run:  pip install \".[{spec.extra}]\"   "
               f"(or just: pip install {module})" if spec.extra
               else f"Run:  pip install {module}")
        raise MissingRuntimeError(
            f"Model '{spec.id}' needs the '{module}' package, which is not installed. {how}"
        ) from e


def _log(message):
    print(message, file=sys.stderr)


def sigmoid(x):
    if x >= 0:
        return 1.0 / (1.0 + math.exp(-x))
    e = math.exp(x)
    return e / (1.0 + e)


def device_pref(device=None):
    """Normalise a device intent: None / '' / unset env -> 'auto'; 'gpu' -> 'cuda'."""
    d = (device or os.environ.get("AI_DETECT_DEVICE") or "auto").strip().lower()
    return "cuda" if d == "gpu" else d


def resolve_torch_device(pref=None):
    """Pick a torch device. pref: 'auto' | 'cpu' | 'cuda' (or None -> env/auto)."""
    import torch

    pref = device_pref(pref)
    if pref == "cpu":
        return torch.device("cpu")
    if pref == "cuda":
        if torch.cuda.is_available():
            return torch.device("cuda")
        _log("Requested GPU but no CUDA device is available — falling back to CPU.")
        return torch.device("cpu")
    return torch.device("cuda" if torch.cuda.is_available() else "cpu")


ONNX_GPU_PROVIDERS = ("DmlExecutionProvider", "CUDAExecutionProvider", "ROCMExecutionProvider")
ONNX_GPU_BUILDS = ("onnxruntime-directml", "onnxruntime-gpu")
ONNX_GPU_HINT = (
    "To run the ONNX models on a GPU, replace the CPU build of ONNX Runtime with a GPU "
    "build (they cannot be installed side by side):  pip uninstall -y onnxruntime  then  "
    "pip install --force-reinstall onnxruntime-directml  (Windows, DirectML)  or  "
    "pip install --force-reinstall onnxruntime-gpu  (NVIDIA CUDA)."
)


def _installed_onnx_builds():
    """Which onnxruntime distributions pip knows about in this environment."""
    from importlib import metadata
    found = []
    for name in ("onnxruntime",) + ONNX_GPU_BUILDS:
        try:
            metadata.version(name)
            found.append(name)
        except metadata.PackageNotFoundError:
            pass
    return found


def onnx_providers(ort, device):
    """The execution providers for an ONNX model, in order.

    CPU is always last, and is the whole answer when no GPU provider is in the
    installed onnxruntime build (the plain ``onnxruntime`` wheel on Windows,
    Linux and macOS has none this function selects) or when the device is
    'cpu'. A GPU provider is used only from a GPU build of ONNX Runtime:
    ``onnxruntime-directml`` (DmlExecutionProvider, Windows) or
    ``onnxruntime-gpu`` (CUDAExecutionProvider). CoreML, which the macOS wheel
    carries, is not selected: it is untested with these quantised models.
    """
    available = ort.get_available_providers()
    pref = device_pref(device)
    if pref == "cpu":
        return ["CPUExecutionProvider"]
    chosen = [p for p in ONNX_GPU_PROVIDERS if p in available]
    if not chosen:
        builds = _installed_onnx_builds()
        clash = [b for b in builds if b in ONNX_GPU_BUILDS]
        if clash and "onnxruntime" in builds:
            _log(f"{clash[0]} is installed beside onnxruntime, and the CPU build has "
                 f"overwritten it, so no GPU provider is available. {ONNX_GPU_HINT}")
        elif pref == "cuda":
            _log(f"Requested GPU but no GPU execution provider is installed; using CPU. "
                 f"{ONNX_GPU_HINT}")
    return chosen + ["CPUExecutionProvider"]


class Backend:
    """Shared plumbing: the spec, a lock, normalisation and batching."""

    def __init__(self, spec, device=None):
        self.spec = spec
        self.name = spec.id
        self.device_label = "cpu"
        # One inference at a time per loaded model: the MCP and web servers can
        # run several detections concurrently and one device serialises anyway.
        self._lock = threading.Lock()
        self._normalize = normalizer(spec.normalizer)

    def _margins_batch(self, batch):  # pragma: no cover - interface
        raise NotImplementedError

    def margins(self, texts):
        texts = [self._normalize(t) for t in texts]
        out = []
        with self._lock:
            for start in range(0, len(texts), BATCH_SIZE):
                out.extend(float(m) for m in self._margins_batch(texts[start:start + BATCH_SIZE]))
        return out

    def score(self, texts):
        return [sigmoid(m) for m in self.margins(texts)]


class DesklibBackend(Backend):
    """DeBERTa-v3-large with desklib's mean-pooled single-logit head."""

    def __init__(self, spec, device=None):
        super().__init__(spec, device)
        import torch
        import torch.nn as nn
        from transformers import AutoConfig, AutoModel, AutoTokenizer, PreTrainedModel

        self._torch = torch

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
                return {"logits": self.classifier(sum_embeddings / sum_mask)}

        self.device = resolve_torch_device(device)
        self.device_label = str(self.device)
        _log("Loading model...")
        self.tokenizer = AutoTokenizer.from_pretrained(spec.repo)
        dtype = torch.float32
        if self.device.type == "cuda" and torch.cuda.is_bf16_supported():
            dtype = torch.bfloat16
        self.model = DesklibAIDetectionModel.from_pretrained(spec.repo, dtype=dtype)
        self.model.to(self.device).eval()
        _log(f"Model loaded on {self.device} ({spec.label})")

    def _margins_batch(self, batch):
        torch = self._torch
        enc = self.tokenizer(batch, padding=True, truncation=True,
                             max_length=MAX_TOKENS, return_tensors="pt").to(self.device)
        with torch.inference_mode():
            logits = self.model(input_ids=enc["input_ids"],
                                attention_mask=enc["attention_mask"])["logits"]
        return logits.float().reshape(-1).tolist()


class HFSequenceClassifierBackend(Backend):
    """Any two-label ``AutoModelForSequenceClassification`` checkpoint
    (label 0 = human, label 1 = AI)."""

    def __init__(self, spec, device=None):
        super().__init__(spec, device)
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self.device = resolve_torch_device(device)
        self.device_label = str(self.device)
        _log("Loading model...")
        kwargs = {"subfolder": spec.subfolder} if spec.subfolder else {}
        self.tokenizer = AutoTokenizer.from_pretrained(spec.repo, **kwargs)
        self.model = AutoModelForSequenceClassification.from_pretrained(spec.repo, **kwargs)
        self.model.to(self.device).eval()
        _log(f"Model loaded on {self.device} ({spec.label})")

    def _margins_batch(self, batch):
        torch = self._torch
        enc = self.tokenizer(batch, padding=True, truncation=True,
                             max_length=MAX_TOKENS, return_tensors="pt").to(self.device)
        with torch.inference_mode():
            logits = self.model(**enc).logits.float()
        return (logits[:, 1] - logits[:, 0]).tolist()


class OnnxBackend(Backend):
    """A two-logit ONNX classifier run through onnxruntime, tokenised with the
    ``tokenizers`` library straight from the repo's tokenizer.json."""

    _PAD_TOKENS = ("[PAD]", "<pad>")

    def __init__(self, spec, device=None):
        super().__init__(spec, device)
        np = _import("numpy", spec)
        ort = _import("onnxruntime", spec)
        tokenizers = _import("tokenizers", spec)
        from huggingface_hub import hf_hub_download

        self._np = np
        _log(f"Loading {spec.label} (ONNX)...")
        paths = {f: hf_hub_download(spec.repo, filename=f) for f in spec.files}
        self.tokenizer = tokenizers.Tokenizer.from_file(paths[spec.tokenizer_file])
        pad = next((t for t in self._PAD_TOKENS
                    if self.tokenizer.token_to_id(t) is not None), None)
        if pad is None:
            raise RuntimeError(f"No pad token found in the tokenizer of {spec.repo}")
        self.tokenizer.enable_padding(pad_id=self.tokenizer.token_to_id(pad), pad_token=pad)
        self.tokenizer.enable_truncation(max_length=MAX_TOKENS)

        onnx_file = next(f for f in spec.files if f.endswith(".onnx"))
        self.session = ort.InferenceSession(
            paths[onnx_file], providers=onnx_providers(ort, device))
        self.input_names = [i.name for i in self.session.get_inputs()]
        self.device_label = self.session.get_providers()[0]
        _log(f"Model loaded via onnxruntime {self.device_label} ({spec.label})")

    def _margins_batch(self, batch):
        np = self._np
        encoded = self.tokenizer.encode_batch(batch)
        ids = np.array([e.ids for e in encoded], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encoded], dtype=np.int64)
        feeds = {}
        for name in self.input_names:
            if "mask" in name:
                feeds[name] = mask
            elif "type" in name:
                feeds[name] = np.zeros_like(ids)
            else:
                feeds[name] = ids
        logits = self.session.run(None, feeds)[0]
        return (logits[:, 1] - logits[:, 0]).tolist()


class ConParaBackend(Backend):
    """DeBERTa-ConPara: a plain state dict with a small custom head.

    Its authors' loader calls ``torch.load(..., weights_only=False)``, which
    executes whatever the pickle contains. This loader does not: it uses
    ``weights_only=True`` and allow-lists only the numpy array types the
    checkpoint's metadata needs, so no code in the file can run.
    """

    BACKBONE = "microsoft/deberta-v3-large"

    def __init__(self, spec, device=None):
        super().__init__(spec, device)
        import numpy as np
        import torch
        import torch.nn as nn
        from huggingface_hub import hf_hub_download
        from transformers import AutoConfig, AutoModel, AutoTokenizer

        _import("sentencepiece", spec)
        from ._vendor.conpara_unicode import unicode_normalize
        self._normalize = lambda t: " ".join(unicode_normalize(str(t)).split())
        self._torch = torch
        self.device = resolve_torch_device(device)
        self.device_label = str(self.device)
        _log("Loading model...")

        try:
            import numpy._core.multiarray as multiarray
        except ImportError:  # numpy 1.x
            import numpy.core.multiarray as multiarray
        allowed = [
            (multiarray._reconstruct, "numpy.core.multiarray._reconstruct"),
            (multiarray._reconstruct, "numpy._core.multiarray._reconstruct"),
            np.ndarray, np.dtype,
            *(getattr(np.dtypes, n) for n in ("Int64DType", "Float64DType", "Float32DType")),
        ]
        path = hf_hub_download(spec.repo, filename=spec.cache_probe)
        with torch.serialization.safe_globals(allowed):
            checkpoint = torch.load(path, map_location="cpu", weights_only=True)
        state = checkpoint.get("model_state_dict", checkpoint)
        self.threshold_margin = float(checkpoint.get("threshold_margin", 0.0))

        class NoFeat(nn.Module):
            def __init__(self, backbone):
                super().__init__()
                self.encoder = AutoModel.from_config(AutoConfig.from_pretrained(backbone))
                self.classifier = nn.Sequential(
                    nn.Linear(1024, 512), nn.GELU(), nn.Dropout(0.1), nn.Linear(512, 2))

            def forward(self, input_ids, attention_mask):
                hidden = self.encoder(input_ids=input_ids,
                                      attention_mask=attention_mask).last_hidden_state
                return self.classifier(hidden[:, 0])

        self.model = NoFeat(self.BACKBONE)
        self.model.load_state_dict(state, strict=True)  # strict: a mismatch is a wrong model
        self.model.to(self.device).eval()
        self.tokenizer = AutoTokenizer.from_pretrained(self.BACKBONE)
        _log(f"Model loaded on {self.device} ({spec.label})")

    def _margins_batch(self, batch):
        torch = self._torch
        enc = self.tokenizer(batch, padding=True, truncation=True,
                             max_length=MAX_TOKENS, return_tensors="pt").to(self.device)
        with torch.inference_mode():
            logits = self.model(enc["input_ids"], enc["attention_mask"]).float()
        return (logits[:, 1] - logits[:, 0]).tolist()


LOADERS = {
    "conpara": ConParaBackend,
    "desklib": DesklibBackend,
    "hf-seqcls": HFSequenceClassifierBackend,
    "onnx": OnnxBackend,
}


def load_backend(spec, device=None):
    try:
        cls = LOADERS[spec.loader]
    except KeyError:
        raise ValueError(f"Model '{spec.id}' names an unknown loader '{spec.loader}'") from None
    return cls(spec, device=device)
