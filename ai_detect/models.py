"""The detectors ai-detect can run. See registry.py for the record format.

Sources for every row, all read 24 Nov 2026:

* Licence, parameter count and file sizes: the Hugging Face API
  (``https://huggingface.co/api/models/<repo>`` and ``.../tree/main``) and the
  model card at ``https://huggingface.co/<repo>``.
* RAID rank: every ``leaderboard/submissions/*/results.json`` in
  https://github.com/liamdugan/raid at commit 84c2ea4 (16 Nov 2026), ranked on
  ``score_agg.all.accuracy["0.05"]`` (TPR at 5% FPR, all attacks, the
  leaderboard's default view). 61 submissions carry that score.

A RAID rank describes the checkpoint its authors submitted, scored on whole
documents. It says nothing certain about a quantised export of that checkpoint
or about single sentences. Where the file ai-detect runs is not the file that
was ranked, the spec's caveats say so.
"""

from .registry import ModelSpec, RaidResult, Registry

_HF = "https://huggingface.co/"
_SHORT = "Trained and benchmarked on whole documents; single-sentence scores are a rough signal."
_SHARE_ALIKE = (
    "Weights are CC BY-SA 4.0: attribution and share-alike apply if you "
    "redistribute or adapt the weights. ai-detect downloads them from the "
    "authors' repo at run time and does not redistribute them."
)

REGISTRY = Registry([
    ModelSpec(
        id="desklib",
        label="desklib/ai-text-detector-v1.01 (DeBERTa-v3-large)",
        summary="The original default. DeBERTa-v3-large, 434M parameters.",
        loader="desklib",
        repo="desklib/ai-text-detector-v1.01",
        files=("*.json", "spm.model", "model.safetensors"),
        cache_probe="model.safetensors",
        approx_mb=1736,
        params_m=434.0,
        licence="MIT",
        licence_source=_HF + "desklib/ai-text-detector-v1.01",
        runtime="torch",
        raid=RaidResult(42, 61, 0.9117, "desklib-ai-text-detector-v1.01",
                        note="First on RAID when submitted, 16 Feb 2025."),
        caveats=(
            _SHORT,
            "Runs bfloat16 on CUDA and float32 on CPU, so scores differ slightly by device.",
        ),
    ),
    ModelSpec(
        id="light",
        label="TMR ai-text-detector (RoBERTa-base, int8 ONNX)",
        summary="Small and fast. RoBERTa-base, 125M parameters, int8 ONNX.",
        loader="onnx",
        repo="onnx-community/tmr-ai-text-detector-ONNX",
        files=("onnx/model_int8.onnx", "tokenizer.json", "tokenizer_config.json",
               "config.json", "special_tokens_map.json"),
        cache_probe="onnx/model_int8.onnx",
        tokenizer_file="tokenizer.json",
        approx_mb=126,
        params_m=124.6,
        licence="MIT",
        licence_source=_HF + "onnx-community/tmr-ai-text-detector-ONNX",
        runtime="onnx",
        raid=RaidResult(36, 61, 0.9579, "tmr_50k",
                        note="Rank is for the fp32 weights at Oxidane/tmr-ai-text-detector; "
                             "ai-detect runs the int8 ONNX export."),
        caveats=(_SHORT,),
        aliases=("tmr",),
    ),
    ModelSpec(
        id="gpttrace-150m",
        label="GPTTrace Ettin-150M v5e (int8 ONNX)",
        summary="Highest-ranked small open model. Ettin-150M, int8 ONNX, 151 MB.",
        loader="onnx",
        repo="nakas/gpttrace-ettin150-text-v5e",
        files=("onnx/model_quantized.onnx", "tokenizer.json", "tokenizer_config.json"),
        cache_probe="onnx/model_quantized.onnx",
        tokenizer_file="tokenizer.json",
        approx_mb=151,
        params_m=150.0,
        licence="CC-BY-SA-4.0",
        licence_source=_HF + "nakas/gpttrace-ettin150-text-v5e",
        runtime="onnx",
        normalizer="invisible+lookalike",
        raid=RaidResult(4, 61, 0.9980, "gpttrace-ettin150",
                        note="The card says the int8 file scores slightly below the "
                             "PyTorch weights (AUC 0.975 vs 0.990 on 300 MAGE texts)."),
        caveats=(
            _SHORT,
            "Its card: text under about 150 words is unreliable for any detector; "
            "paraphrased AI text is caught much less often.",
            _SHARE_ALIKE,
        ),
        aliases=("gpttrace", "gpttrace-150"),
    ),
    ModelSpec(
        id="gpttrace-1b",
        label="GPTTrace Ettin-1B v8s (4-bit ONNX)",
        summary="Highest-ranked open model. Ettin-1B, 4-bit ONNX for CPU, 951 MB.",
        loader="onnx",
        repo="nakas/gpttrace-v8s-1b",
        files=("onnx/model.onnx", "onnx/model.onnx.data", "onnx/tokenizer.json",
               "onnx/tokenizer_config.json"),
        cache_probe="onnx/model.onnx.data",
        tokenizer_file="onnx/tokenizer.json",
        approx_mb=951,
        params_m=None,
        licence="CC-BY-SA-4.0",
        licence_source=_HF + "nakas/gpttrace-v8s-1b",
        runtime="onnx",
        normalizer="invisible+lookalike",
        raid=RaidResult(2, 61, 0.9993, "gpttrace-ettin1b",
                        note="Rank is for the full-precision weights (4.13 GB). ai-detect "
                             "runs the repo's 4-bit ONNX export; the card reports AUROC "
                             "0.9955 vs 0.9958 and 99% sign agreement on 300 MAGE texts."),
        caveats=(
            _SHORT,
            "Its card: formal or academic prose by non-native writers is flagged more "
            "often at the raw cut-off; commercial humanizer output is caught less often.",
            _SHARE_ALIKE,
        ),
        aliases=("gpttrace-v8s",),
    ),
    ModelSpec(
        id="tabularis",
        label="Tabularis ModernBERT R1.1",
        summary="MIT-licensed ModernBERT-base, 150M parameters.",
        loader="hf-seqcls",
        repo="tabularisai/ai-text-detection",
        files=("*.json", "model.safetensors"),
        cache_probe="model.safetensors",
        approx_mb=598,
        params_m=149.6,
        licence="MIT",
        licence_source=_HF + "tabularisai/ai-text-detection",
        runtime="torch",
        normalizer="nfkc",
        raid=RaidResult(21, 61, 0.9898, "tabularis-modernbert-r1",
                        note="Leaderboard entry name: Tabularis ModernBERT R1.1 (NFKC)."),
        caveats=(_SHORT,),
        aliases=("modernbert",),
    ),
    ModelSpec(
        id="conpara",
        label="DeBERTa-ConPara (DeBERTa-v3-large)",
        summary="MIT-licensed DeBERTa-v3-large, same size as desklib, ranked far higher.",
        loader="conpara",
        repo="SES-Lab-OTH/deberta-conpara",
        files=("rawguard.pt",),
        cache_probe="rawguard.pt",
        extra_repos=(("microsoft/deberta-v3-large",
                      ("config.json", "tokenizer_config.json", "spm.model")),),
        approx_mb=1738,
        params_m=None,
        licence="MIT",
        licence_source=_HF + "SES-Lab-OTH/deberta-conpara",
        runtime="torch",
        extra="conpara",
        normalizer="none",  # the backend applies the authors' own normaliser
        raid=RaidResult(20, 61, 0.9901, "DeBERTa-ConPara"),
        caveats=(
            _SHORT,
            "Its card: below about 60 words errors rise four to five times; under 25 "
            "words the score is meaningless. The output is a logit margin, not a "
            "calibrated probability, and saturates at the extremes.",
            "Its card: false-positive rates of 13% to 67% on academic prose.",
            "Needs the sentencepiece package (pip install \".[conpara]\").",
        ),
    ),
])

MODELS = REGISTRY.models
DEFAULT_MODEL = "gpttrace-150m"
