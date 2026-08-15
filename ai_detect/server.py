#!/usr/bin/env python3
"""
MCP server for ai-detect.

Exposes AI-text detection over the Model Context Protocol (stdio) so any MCP
client (Claude Desktop, Claude Code, etc.) can score copy, sentence by sentence,
with pattern diagnostics that explain *why* each sentence looks AI-written.

Tools:
  * detect_ai_text   — analyse a string of text
  * detect_ai_file   — analyse a local file (keeps large drafts out of the
                       client's context window — the server reads the file)
  * compare_texts    — analyse two texts and report both scores
  * get_model_status — is a model downloaded yet, and how big is it
  * list_models      — list available detection models (with downloaded flags)

First-run note: the default model is ~1.7 GB. Because that download blocks the
first detect call for minutes, **call get_model_status first** — it returns
instantly and tells you whether a download is pending, so you can warn the user
before the long call rather than looking like the server has hung.

Run: ai-detect-mcp   (or: python -m ai_detect.server)
"""

import os
import threading

from mcp.server.fastmcp import FastMCP

from .detector import (
    DEFAULT_MODEL,
    MODELS,
    classify_text,
    is_model_cached,
    preload_dependencies,
    prefetch_model,
    verdict,
)

mcp = FastMCP("ai-detect")

# The heavy ML deps (torch/transformers/onnxruntime) are imported in a background
# thread at startup so the MCP `initialize` handshake returns immediately — clients
# enforce a short connect budget (Claude Desktop drops the whole server if it isn't
# ready within ~10s, which made every OTHER server look disconnected too). The
# import must still happen in ONE dedicated thread: a first-time import of these
# C-extension modules from a request worker thread can deadlock the import
# machinery (see preload_dependencies). So detection tools call _await_ready()
# first — an early call blocks on this Event until the preload thread finishes,
# then hits a warm sys.modules cache instead of importing on the worker thread.
_preload_done = threading.Event()


def _preload_in_background():
    try:
        preload_dependencies()
        # Also pull the default model's weights to disk (no device load) so the
        # first detect call doesn't eat a ~1.7 GB download. No-op once cached.
        prefetch_model(DEFAULT_MODEL)
    finally:
        _preload_done.set()


def _await_ready():
    """Block until the startup preload thread has imported the heavy deps."""
    _preload_done.wait()


def _summarise(data, include_all_sentences=False):
    """Shape a classify_text() report for MCP consumers.

    Returns a compact summary plus the AI-flagged sentences (with diagnostics).
    Set include_all_sentences=True to also return every scored sentence.
    """
    flagged = [
        {
            "sentence": s["sentence"],
            "ai_prob": s["ai_prob"],
            "diagnostics": s["diagnostics"],
        }
        for s in data["sentences"]
        if s["label"] == "AI"
    ]
    out = {
        "model": data.get("model"),
        "model_ai_pct": data["model_ai_pct"],
        "verdict": verdict(data["model_ai_pct"]),
        "counts": {
            "ai": data["ai_count"],
            "human": data["human_count"],
            "skipped": data["skipped_count"],
            "total": data["total"],
        },
        "text_metrics": data["text_metrics"],
        "pattern_totals": data["pattern_totals"],
        "flagged_sentences": flagged,
    }
    if include_all_sentences:
        out["all_sentences"] = data["sentences"]
    return out


def _dev(device):
    return None if device in (None, "auto") else device


@mcp.tool()
def detect_ai_text(
    text: str,
    model: str = DEFAULT_MODEL,
    device: str = "auto",
    include_all_sentences: bool = False,
) -> dict:
    """Detect AI-generated text, sentence by sentence.

    Args:
        text: The text to analyse.
        model: 'desklib' (default, most accurate, ~1.7GB) or 'light' (small ONNX, ~126MB).
        device: 'auto' (GPU if available, else CPU), 'cpu', or 'cuda'.
        include_all_sentences: Also return every scored sentence, not just AI-flagged ones.

    First-run note: if the model isn't downloaded yet this call blocks while it
    fetches from Hugging Face (the default is ~1.7 GB). Call get_model_status
    first so you can warn the user about the wait. Returns an overall AI score,
    verdict, per-sentence AI-flagged findings, style pattern totals, and
    sentence-length variation (SDSL) metrics.
    """
    _await_ready()
    data = classify_text(text, model=model, device=_dev(device))
    return _summarise(data, include_all_sentences=include_all_sentences)


@mcp.tool()
def detect_ai_file(
    path: str,
    model: str = DEFAULT_MODEL,
    device: str = "auto",
    include_all_sentences: bool = False,
) -> dict:
    """Detect AI-generated text in a local file (the server reads it, so large
    drafts never enter the client's context window).

    Args:
        path: Absolute path to a UTF-8 text file.
        model: 'desklib' (default) or 'light'.
        device: 'auto', 'cpu', or 'cuda'.
        include_all_sentences: Also return every scored sentence, not just AI-flagged ones.

    First-run note: see detect_ai_text — call get_model_status first if the model
    may still need downloading.
    """
    _await_ready()
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No such file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    data = classify_text(text, model=model, device=_dev(device))
    result = _summarise(data, include_all_sentences=include_all_sentences)
    result["file"] = path
    return result


@mcp.tool()
def compare_texts(
    text_a: str,
    text_b: str,
    model: str = DEFAULT_MODEL,
    device: str = "auto",
) -> dict:
    """Analyse two texts and report both AI scores (e.g. a draft vs an edit)."""
    _await_ready()
    dev = _dev(device)
    a = classify_text(text_a, model=model, device=dev)
    b = classify_text(text_b, model=model, device=dev)
    return {
        "a": _summarise(a),
        "b": _summarise(b),
        "delta_ai_pct": round(a["model_ai_pct"] - b["model_ai_pct"], 1),
    }


@mcp.tool()
def get_model_status(model: str = DEFAULT_MODEL) -> dict:
    """Check whether a detection model is already downloaded, and its size.

    Returns instantly. Call this before a first detection so you can tell the
    user if a one-time download is pending — the default model is ~1.7 GB and can
    take a few minutes, during which the detect call blocks. Checking first is how
    you avoid the call looking like the server has hung.
    """
    cfg = MODELS.get(model)
    if not cfg:
        return {"error": f"Unknown model '{model}'", "available": list(MODELS)}
    cached = is_model_cached(model)
    return {
        "model": model,
        "label": cfg["label"],
        "approx_mb": cfg["approx_mb"],
        "downloaded": cached,
        "note": (
            "Ready — cached locally, detection starts immediately."
            if cached else
            f"Not downloaded yet. The first detect call fetches ~{cfg['approx_mb']} MB "
            "from Hugging Face (one-time, then cached); the call will block for up to "
            "a few minutes. Warn the user before running detection."
        ),
    }


@mcp.tool()
def list_models() -> dict:
    """List available detection models, their sizes, and whether each is downloaded."""
    return {
        "default": DEFAULT_MODEL,
        "models": {
            name: {
                "label": cfg["label"],
                "approx_mb": cfg["approx_mb"],
                "downloaded": is_model_cached(name),
            }
            for name, cfg in MODELS.items()
        },
    }


def main():
    # Warm the heavy deps (and pre-download the default model) in the background so
    # the stdio loop — and the MCP initialize handshake — starts immediately.
    # Detection tools call _await_ready(), so the first import still happens once,
    # in this dedicated preload thread, never on a request worker thread (which can
    # deadlock — see preload_dependencies and _await_ready).
    threading.Thread(
        target=_preload_in_background, name="ai-detect-preload", daemon=True
    ).start()
    mcp.run()


if __name__ == "__main__":
    main()
