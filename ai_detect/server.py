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

First-run note: the default model is ~1.7 GB. The server starts fetching it in
the background as soon as it launches, but until that finishes a detect call has
to wait for it. **Call get_model_status first** — it returns instantly and tells
you whether the model is ready, still downloading, or absent, so you can warn the
user before the long call rather than looking like the server has hung.

Run: ai-detect-mcp   (or: python -m ai_detect.server)
"""

import functools
import os
import threading

import anyio.to_thread
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
#
# Nothing may block on this Event from the event-loop thread: FastMCP invokes sync
# tool functions inline in the request coroutine, so a sync tool that waited here
# would freeze the whole stdio loop (no reads, no pings, no cancellation) for the
# length of a multi-minute model download. Every tool that can block is therefore
# `async def` and hands the blocking part to anyio.to_thread.
_preload_done = threading.Event()
_preload_error = None

# How long a detect call will wait for the startup preload before giving up. The
# preload includes a one-time ~1.7 GB download, so the default is generous; the
# point is that a wedged download (half-open socket, hub outage in long backoff)
# surfaces as an error instead of hanging the tool forever. 0 = wait indefinitely.
READY_TIMEOUT = float(os.environ.get("AI_DETECT_READY_TIMEOUT", "900"))

# Model download state, published by the preload thread so get_model_status can
# answer without importing anything (and so it can say "downloading" rather than
# mis-reporting an in-flight fetch as "you'll need to download this").
_STATE_UNKNOWN = "unknown"
_model_states = {name: _STATE_UNKNOWN for name in MODELS}
_state_lock = threading.Lock()


def _set_state(model, state):
    with _state_lock:
        _model_states[model] = state


def _preload_in_background():
    """Import the heavy deps, then pull the default model's weights to disk.

    Runs once, in its own thread, started before mcp.run(). Records progress in
    _model_states as it goes. Never raises: a failure is stored in _preload_error
    and re-raised to whichever tool call is waiting, so the client gets a real
    error rather than a silent hang.
    """
    global _preload_error
    try:
        # Probe the cache first — it only needs huggingface_hub, so status tools
        # get a truthful answer within a moment of startup rather than after the
        # full torch import.
        for name in MODELS:
            _set_state(name, "ready" if is_model_cached(name) else "absent")

        preload_dependencies()

        if not is_model_cached(DEFAULT_MODEL):
            _set_state(DEFAULT_MODEL, "downloading")
            ok = prefetch_model(DEFAULT_MODEL)
            _set_state(DEFAULT_MODEL, "ready" if ok else "absent")
    except Exception as e:  # pragma: no cover - defensive; the callees swallow their own
        _preload_error = e
    finally:
        _preload_done.set()


def _await_ready():
    """Block until the startup preload thread has imported the heavy deps.

    MUST be called from a worker thread, never the event loop. Raises TimeoutError
    if the preload is still running after READY_TIMEOUT, and re-raises whatever
    the preload thread failed with.
    """
    timeout = READY_TIMEOUT if READY_TIMEOUT > 0 else None
    if not _preload_done.wait(timeout):
        raise TimeoutError(
            f"ai-detect: model startup did not finish within {READY_TIMEOUT:.0f}s "
            f"(state: {_model_states.get(DEFAULT_MODEL, _STATE_UNKNOWN)}). The "
            "Hugging Face download may be stalled — check the network and restart "
            "the server, or raise AI_DETECT_READY_TIMEOUT."
        )
    if _preload_error is not None:
        raise RuntimeError(f"ai-detect: model startup failed: {_preload_error}")


async def _offload(fn, *args, **kwargs):
    """Run a blocking detection call in a worker thread, keeping the loop free."""
    return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs))


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


# ---------------------------------------------------------------------------
# Blocking workers — each runs in a thread via _offload()
# ---------------------------------------------------------------------------

def _run_detect(text, model, device, include_all_sentences):
    _await_ready()
    data = classify_text(text, model=model, device=_dev(device))
    return _summarise(data, include_all_sentences=include_all_sentences)


def _run_detect_file(path, model, device, include_all_sentences):
    # Validate and read BEFORE waiting on the model: a bad path should fail in
    # milliseconds, not after a multi-minute download that was never needed.
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No such file: {path}")
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    result = _run_detect(text, model, device, include_all_sentences)
    result["file"] = path
    return result


def _run_compare(text_a, text_b, model, device):
    _await_ready()
    dev = _dev(device)
    a = classify_text(text_a, model=model, device=dev)
    b = classify_text(text_b, model=model, device=dev)
    return {
        "a": _summarise(a),
        "b": _summarise(b),
        "delta_ai_pct": round(a["model_ai_pct"] - b["model_ai_pct"], 1),
    }


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def detect_ai_text(
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

    First-run note: if the model isn't downloaded yet this call waits for the
    background fetch from Hugging Face (the default is ~1.7 GB). Call
    get_model_status first so you can warn the user about the wait. Returns an
    overall AI score, verdict, per-sentence AI-flagged findings, style pattern
    totals, and sentence-length variation (SDSL) metrics.
    """
    return await _offload(_run_detect, text, model, device, include_all_sentences)


@mcp.tool()
async def detect_ai_file(
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
    return await _offload(_run_detect_file, path, model, device, include_all_sentences)


@mcp.tool()
async def compare_texts(
    text_a: str,
    text_b: str,
    model: str = DEFAULT_MODEL,
    device: str = "auto",
) -> dict:
    """Analyse two texts and report both AI scores (e.g. a draft vs an edit)."""
    return await _offload(_run_compare, text_a, text_b, model, device)


def _model_state(model):
    """Current download state of a model: 'ready', 'downloading', 'absent', 'unknown'.

    Deliberately import-free while the preload thread is still running: probing the
    cache means importing huggingface_hub, and doing that on the event-loop thread
    while another thread is mid-import of the same dependency graph is the exact
    deadlock hazard preload_dependencies() exists to avoid. Once the preload has
    finished, the import is a warm cache hit and the live probe is safe (and more
    accurate — it picks up a model downloaded by some other process).
    """
    if _preload_done.is_set():
        state = "ready" if is_model_cached(model) else "absent"
        _set_state(model, state)
        return state
    with _state_lock:
        return _model_states.get(model, _STATE_UNKNOWN)


_STATE_NOTES = {
    "ready": "Ready — cached locally, detection starts immediately.",
    "downloading": (
        "Downloading now in the background (started at server launch). A detect "
        "call will wait for it to finish rather than starting a second download — "
        "tell the user it may take a few minutes."
    ),
    "absent": (
        "Not downloaded. The next detect call fetches it from Hugging Face "
        "(one-time, then cached) and will block for up to a few minutes. Warn the "
        "user before running detection."
    ),
    _STATE_UNKNOWN: (
        "Server is still starting up and hasn't checked the cache yet. Call again "
        "in a moment for a definite answer."
    ),
}


@mcp.tool()
def get_model_status(model: str = DEFAULT_MODEL) -> dict:
    """Check whether a detection model is downloaded, downloading, or absent.

    Returns instantly. Call this before a first detection so you can tell the user
    if a one-time download is pending — the default model is ~1.7 GB and can take
    a few minutes, during which the detect call waits. Checking first is how you
    avoid the call looking like the server has hung.
    """
    cfg = MODELS.get(model)
    if not cfg:
        return {"error": f"Unknown model '{model}'", "available": list(MODELS)}
    state = _model_state(model)
    return {
        "model": model,
        "label": cfg["label"],
        "approx_mb": cfg["approx_mb"],
        "status": state,
        "downloaded": state == "ready",
        "note": _STATE_NOTES[state],
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
                "status": (state := _model_state(name)),
                "downloaded": state == "ready",
            }
            for name, cfg in MODELS.items()
        },
    }


def main():
    # Warm the heavy deps (and pre-download the default model) in the background so
    # the stdio loop — and the MCP initialize handshake — starts immediately.
    # Detection tools call _await_ready() from a worker thread, so the first import
    # still happens once, in this dedicated preload thread, never on a request
    # worker thread (which can deadlock — see preload_dependencies and _await_ready).
    threading.Thread(
        target=_preload_in_background, name="ai-detect-preload", daemon=True
    ).start()
    mcp.run()


if __name__ == "__main__":
    main()
