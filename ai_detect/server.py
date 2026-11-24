"""MCP server for ai-detect.

Exposes local AI-text detection over the Model Context Protocol (stdio).

Tools
  detect_ai_text    analyse a string
  detect_ai_file    analyse a local file (the server reads it)
  detect_ai_url     fetch one web page and analyse it
  compare_texts     analyse two texts and report the change
  scan_batch        analyse many files / URLs, one summary row each
  get_model_status  is a model ready, downloading (with progress), absent or failed
  list_models       every model with licence, size, RAID rank and status
  prefetch          start downloading a model now
  open_dashboard    start the local web UI and return its URL

Two rules shape this file.

1. Nothing blocks on a download. A tool that needs a model that is not on disk
   starts the download in the background and returns at once with
   ``status: "downloading"``, progress figures, the dashboard URL and one
   sentence the client can relay. The caller asks again later.

2. Nothing blocks the event loop, and the heavy ML libraries are imported once,
   in one dedicated thread, before any worker thread touches them (a first
   import of torch/transformers from a request worker can deadlock the import
   machinery). Every tool that can take time is ``async`` and hands its work to
   a worker thread, which first waits for that preload.

Run: ai-detect-mcp   (or: python -m ai_detect.server)
"""

import functools
import os
import threading

import anyio.from_thread
import anyio.to_thread

try:  # MCP Python SDK 2.x
    from mcp.server.mcpserver import Context, MCPServer as _Server
except ImportError:  # SDK 1.x
    from mcp.server.fastmcp import Context, FastMCP as _Server

try:
    from mcp.types import ToolAnnotations
except ImportError:  # pragma: no cover - annotations are optional metadata
    ToolAnnotations = None

from . import downloads, history
from .detector import DEFAULT_MODEL, preload_dependencies, verdict
from .models import MODELS, REGISTRY
from .web import server as dashboard

INSTRUCTIONS = (
    "ai-detect scores text for AI authorship on this machine. Text, files and fetched pages "
    "never leave it; the only network traffic is model downloads from Hugging Face and the "
    "one page a URL tool is asked to fetch.\n"
    "Models download on first use and are cached: "
    + ", ".join(f"{m} {s.approx_mb} MB" for m, s in MODELS.items())
    + f". The default is {DEFAULT_MODEL}. A detect call never waits for a download: if the "
    "model is not ready it returns status \"downloading\" with a percentage and a message. "
    "Relay that message to the user and call the tool again in a minute. get_model_status "
    "shows progress for any model; prefetch starts a download ahead of time.\n"
    "Every result carries dashboard_url, a local page with the highlighted text and details. "
    "open_dashboard starts that web UI (http://127.0.0.1:8765 unless the port was busy; the "
    "tool returns the real address) and can open it in the browser.\n"
    "Scores are evidence, not proof. Report the document score with its confidence and "
    "notes; single-sentence scores are a rough signal."
)

mcp = _Server("ai-detect", instructions=INSTRUCTIONS)

_preload_done = threading.Event()
_preload_error = None
READY_TIMEOUT = float(os.environ.get("AI_DETECT_READY_TIMEOUT", "900"))


def _annot(**kw):
    return ToolAnnotations(**kw) if ToolAnnotations else None


_READ = dict(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


def _preload_in_background():
    """Import the heavy libraries in one dedicated thread, then start fetching
    the default model if it is missing. Never raises."""
    global _preload_error
    try:
        preload_dependencies()
        if os.environ.get("AI_DETECT_NO_PREFETCH", "").lower() not in ("1", "true", "yes"):
            downloads.start(DEFAULT_MODEL)
    except Exception as e:  # pragma: no cover - defensive
        _preload_error = e
    finally:
        _preload_done.set()


def _await_ready():
    """Block until the ML libraries are imported. Worker threads only."""
    timeout = READY_TIMEOUT if READY_TIMEOUT > 0 else None
    if not _preload_done.wait(timeout):
        raise TimeoutError(
            f"ai-detect: startup did not finish within {READY_TIMEOUT:.0f}s. Restart the "
            "server, or raise AI_DETECT_READY_TIMEOUT.")
    if _preload_error is not None:
        raise RuntimeError(f"ai-detect: startup failed: {_preload_error}")


async def _offload(fn, *args, **kwargs):
    """Run a blocking call in a worker thread, keeping the event loop free."""
    return await anyio.to_thread.run_sync(functools.partial(fn, *args, **kwargs))


def _dashboard_url():
    """Start the dashboard on first use and return its real URL ('' if it
    cannot start, which must never fail a detection)."""
    try:
        return dashboard.ensure_started()
    except Exception:
        return ""


def _notifier(ctx):
    """A progress callback that forwards to the MCP client from a worker thread:
    progress notifications when the client sent a progressToken (the SDK drops
    them otherwise), and a log line either way."""
    if ctx is None:
        return None

    def notify(event):
        try:
            stage, model = event.get("stage", ""), event.get("model", "")
            index, of = event.get("index", 0), event.get("of", 1)
            done = index + (0.5 if stage == "scoring" else 0)
            message = f"{stage} {model}".strip()
            anyio.from_thread.run(ctx.report_progress, done, of, message)
            anyio.from_thread.run(ctx.info, f"ai-detect: {message}")
        except Exception:
            pass  # a client that does not take notifications must not break a scan
    return notify


def _downloading(statuses):
    """The immediate answer when a needed model is not on disk yet."""
    url = _dashboard_url()
    pending = [s for s in statuses if s["status"] != "ready"]
    failed = [s for s in pending if s["status"] == "failed"]
    first = (failed or pending)[0]
    where = f" Watch progress at {url}/#/models." if url else ""
    again = "" if failed else " Ask me again in a minute."
    return {
        "status": "failed" if failed else "downloading",
        "ready": False,
        "models": statuses,
        "dashboard_url": f"{url}/#/models" if url else "",
        "message": first["message"] + where + again,
    }


def _summarise(data, include_all_sentences=False):
    """Shape a report for MCP consumers: a compact summary plus the flagged
    sentences. The keys the first release returned are all still here."""
    flagged = [
        {"sentence": s["sentence"], "ai_prob": s["ai_prob"], "diagnostics": s["diagnostics"],
         **({"agreement": s["agreement"], "scores": s["scores"]} if len(data["models"]) > 1 else {}),
         "why": s.get("why", [])}
        for s in data["sentences"] if s["label"] == "AI"
    ]
    tells = data.get("tells") or {"structure": [], "visual": [], "summary": {}}
    out = {
        "status": "ok",
        "model": data.get("model"),
        "models": data["models"],
        "model_ai_pct": data["model_ai_pct"],
        "verdict": verdict(data["model_ai_pct"]),
        "document_ai_pct": data["document_ai_pct"],
        "assessment": data.get("assessment"),
        "operating_point": data.get("operating_point"),
        "counts": {"ai": data["ai_count"], "human": data["human_count"],
                   "skipped": data["skipped_count"], "total": data["total"]},
        "text_metrics": {k: v for k, v in data["text_metrics"].items() if k != "lengths"},
        "pattern_totals": data["pattern_totals"],
        "flagged_sentences": flagged,
        "structure_and_style": {
            "note": tells.get("note", ""),
            "counts": tells.get("summary", {}).get("counts", {}),
            "tells": [{k: t[k] for k in ("id", "label", "severity", "example", "suggestion", "detail")}
                      for t in (tells["structure"] + tells["visual"])[:25]],
        },
        "scan_id": data.get("scan_id"),
        "dashboard_url": data.get("dashboard_url", ""),
    }
    if data.get("per_model"):
        out["per_model"] = data["per_model"]
        out["ensemble"] = data["ensemble"]
    if data.get("perplexity"):
        out["perplexity"] = {k: v for k, v in data["perplexity"].items() if k != "per_sentence"}
    if data.get("source"):
        out["source"] = data["source"]
    if include_all_sentences:
        out["all_sentences"] = data["sentences"]
    return out


def _dev(device):
    if device not in (None, "", "auto", "cpu", "cuda", "gpu"):
        raise ValueError(f"Unknown device '{device}'. Use 'auto', 'cpu' or 'cuda'.")
    return None if device in (None, "", "auto") else device


def _scan(source, model, device, perplexity, notify):
    """Shared worker: validate, make sure models are on disk, analyse, save."""
    from .web.app import run_scan
    model_ids = REGISTRY.parse(model, DEFAULT_MODEL)   # a typo fails in milliseconds
    dev = _dev(device)
    ready, statuses = downloads.ensure(model_ids)
    if not ready:
        return None, _downloading(statuses)
    _await_ready()
    _dashboard_url()
    report = run_scan(source, models=model_ids, device=dev, perplexity=perplexity, progress=notify)
    return report, None


def _run_detect(source, model, device, include_all_sentences, perplexity, notify):
    report, pending = _scan(source, model, device, perplexity, notify)
    if pending:
        return pending
    out = _summarise(report, include_all_sentences=include_all_sentences)
    if source.get("file"):
        out["file"] = source["file"]
    if source.get("url"):
        out["url"] = report["source"]["label"]
    return out


def _run_compare(text_a, text_b, model, device, notify):
    from .analyze import compare
    a, pending = _scan({"text": text_a}, model, device, False, notify)
    if pending:
        return pending
    b, _ = _scan({"text": text_b}, model, device, False, notify)
    return {
        "status": "ok",
        "a": _summarise(a), "b": _summarise(b),
        "delta_ai_pct": round(a["model_ai_pct"] - b["model_ai_pct"], 1),
        "change": compare(a, b),
    }


def _run_batch(items, model, device):
    from .web.app import _options, run_batch
    model_ids = REGISTRY.parse(model, DEFAULT_MODEL)
    ready, statuses = downloads.ensure(model_ids)
    if not ready:
        return _downloading(statuses)
    if not items:
        raise ValueError("Give at least one file path or URL.")
    if len(items) > 200:
        raise ValueError("A batch takes at most 200 items.")
    _await_ready()
    url = _dashboard_url()
    sources = [{"url": i} if i.lower().startswith(("http://", "https://")) else {"file": i}
               for i in items]
    result = run_batch(sources, _options({"models": model_ids, "device": _dev(device)}))
    result["status"] = "ok"
    result["dashboard_url"] = f"{url}/#/history" if url else ""
    return result


_DOWNLOAD_NOTE = (
    "May trigger a model download: if the model is not on disk this returns at once with "
    "status \"downloading\" and a progress message instead of a result. Relay the message and "
    "call again later."
)


@mcp.tool(annotations=_annot(title="Detect AI text", **_READ))
async def detect_ai_text(
    text: str,
    model: str = DEFAULT_MODEL,
    device: str = "auto",
    include_all_sentences: bool = False,
    perplexity: bool = False,
    ctx: Context = None,
) -> dict:
    """Score text for AI authorship, sentence by sentence and as a whole document.

    Args:
        text: The text to analyse (plain text or Markdown).
        model: A model id, or up to 5 comma-separated ids to run as an ensemble
            (see list_models). Default 'desklib'.
        device: 'auto' (GPU if available, else CPU), 'cpu', or 'cuda'.
        include_all_sentences: Also return every scored sentence, not just flagged ones.
        perplexity: Add a GPT-2 perplexity and burstiness readout (548 MB on first use).

    Returns the mean sentence score and verdict, the document score with a stated
    confidence, AI-flagged sentences with pattern diagnostics and rewrite suggestions,
    structure-and-style tells (a separate signal), and dashboard_url.

    May trigger a model download: if the model is not on disk this returns at once with
    status "downloading" and a progress message instead of a result.
    """
    return await _offload(_run_detect, {"text": text}, model, device, include_all_sentences,
                          perplexity, _notifier(ctx))


@mcp.tool(annotations=_annot(title="Detect AI text in a file", **_READ))
async def detect_ai_file(
    path: str,
    model: str = DEFAULT_MODEL,
    device: str = "auto",
    include_all_sentences: bool = False,
    perplexity: bool = False,
    ctx: Context = None,
) -> dict:
    """Score a local file (the server reads it, so a long draft never enters the
    conversation). Text and Markdown are read directly; .html files are rendered
    with headless Chromium (needs the [web] extra).

    Args:
        path: Absolute path to a UTF-8 .txt, .md or .html file.
        model: A model id or comma-separated ids (ensemble). Default 'desklib'.
        device: 'auto', 'cpu', or 'cuda'.
        include_all_sentences: Also return every scored sentence.
        perplexity: Add the GPT-2 perplexity readout.

    May trigger a model download (see detect_ai_text): returns status "downloading"
    at once if the model is not on disk.
    """
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No such file: {path}")
    return await _offload(_run_detect, {"file": path}, model, device, include_all_sentences,
                          perplexity, _notifier(ctx))


@mcp.tool(annotations=_annot(title="Detect AI text on a web page", readOnlyHint=True,
                             destructiveHint=False, idempotentHint=True, openWorldHint=True))
async def detect_ai_url(
    url: str,
    model: str = DEFAULT_MODEL,
    device: str = "auto",
    include_all_sentences: bool = False,
    perplexity: bool = False,
    timeout: float = 30.0,
    ctx: Context = None,
) -> dict:
    """Fetch ONE web page with headless Chromium and score its article text. Also
    reports visual-shape tells (card grids of three, gradient hero, and so on) and
    saves a screenshot to the dashboard. Fetches only this URL: no crawling, no
    form submission, no sign-in. Needs the [web] extra (Playwright).

    Args:
        url: An http(s) address.
        model: A model id or comma-separated ids (ensemble). Default 'desklib'.
        device: 'auto', 'cpu', or 'cuda'.
        include_all_sentences: Also return every scored sentence.
        perplexity: Add the GPT-2 perplexity readout.
        timeout: Seconds to wait for the page.

    May trigger a model download (see detect_ai_text): returns status "downloading"
    at once if the model is not on disk.
    """
    from .fetch import _check_url
    _check_url(url)

    def work():
        from .web.app import run_scan  # noqa: F401  (imported in the worker thread)
        model_ids = REGISTRY.parse(model, DEFAULT_MODEL)
        ready, statuses = downloads.ensure(model_ids)
        if not ready:
            return _downloading(statuses)
        _await_ready()
        _dashboard_url()
        report = run_scan({"url": url}, models=model_ids, device=_dev(device),
                          perplexity=perplexity, timeout=timeout, progress=_notifier(ctx))
        out = _summarise(report, include_all_sentences=include_all_sentences)
        out["url"] = report["source"]["label"]
        return out
    return await _offload(work)


@mcp.tool(annotations=_annot(title="Compare two texts", **_READ))
async def compare_texts(
    text_a: str,
    text_b: str,
    model: str = DEFAULT_MODEL,
    device: str = "auto",
    ctx: Context = None,
) -> dict:
    """Analyse two texts (e.g. a draft and an edit) and report both results and
    the change. May trigger a model download: returns status "downloading" at
    once if the model is not on disk."""
    return await _offload(_run_compare, text_a, text_b, model, device, _notifier(ctx))


@mcp.tool(annotations=_annot(title="Scan many files or URLs", readOnlyHint=True,
                             destructiveHint=False, idempotentHint=True, openWorldHint=True))
async def scan_batch(items: list[str], model: str = DEFAULT_MODEL, device: str = "auto") -> dict:
    """Scan up to 200 file paths and/or URLs one after another and return one
    summary row each (verdict, document score, flagged sentences, tells, scan_id).
    Full results open from the dashboard history. May trigger a model download:
    returns status "downloading" at once if the model is not on disk."""
    return await _offload(_run_batch, items, model, device)


def _status(model):
    s = downloads.status(model)
    legacy = "absent" if s["status"] == "not_downloaded" else s["status"]
    return {**s, "state": s["status"], "status": legacy, "note": s["message"]}


@mcp.tool(annotations=_annot(title="Model status", **_READ))
def get_model_status(model: str = DEFAULT_MODEL) -> dict:
    """Is a model ready, downloading, not downloaded or failed? Returns instantly.

    `status` is 'ready', 'downloading', 'absent' or 'failed' (`state` says the
    same with 'not_downloaded' for absent). While downloading it gives bytes_done,
    bytes_total, percent and eta_seconds; after a failure, the reason in `error`.
    `message` is one sentence to relay. Also returns dashboard_url. Never triggers
    a download.
    """
    if model not in MODELS and model not in REGISTRY.aliases:
        return {"error": f"Unknown model '{model}'", "available": list(MODELS)}
    out = _status(model)
    url = dashboard.url()
    out["dashboard_url"] = f"{url}/#/models" if url else ""
    return out


@mcp.tool(annotations=_annot(title="List models", **_READ))
def list_models() -> dict:
    """List every detection model: size, licence, RAID leaderboard rank (with its
    source and the date it was read), runtime, and download status. Never
    triggers a download."""
    url = dashboard.url()
    return {
        "default": DEFAULT_MODEL,
        "max_ensemble": 5,
        "dashboard_url": f"{url}/#/models" if url else "",
        "models": {name: {**spec.public(), **_status(name)} for name, spec in MODELS.items()},
    }


@mcp.tool(annotations=_annot(title="Download a model", readOnlyHint=False, destructiveHint=False,
                             idempotentHint=True, openWorldHint=True))
def prefetch(model: str = DEFAULT_MODEL) -> dict:
    """Start downloading a model's weights from Hugging Face in the background so
    the first detection is not delayed. `model` is an id, or 'all'. Returns at
    once with progress; poll get_model_status. A failed or interrupted download
    is resumed by calling this again."""
    ids = list(MODELS) if model == "all" else [REGISTRY.resolve(model).id]
    url = _dashboard_url()
    statuses = [downloads.start(m) for m in ids]
    for s in statuses:
        s["state"] = s["status"]
    return {
        "models": statuses,
        "dashboard_url": f"{url}/#/models" if url else "",
        "message": " ".join(s["message"] for s in statuses),
    }


@mcp.tool(annotations=_annot(title="Open the dashboard", readOnlyHint=False,
                             destructiveHint=False, idempotentHint=True, openWorldHint=False))
def open_dashboard(open_browser: bool = False) -> dict:
    """Start the local web UI (bound to 127.0.0.1) and return its URL. It shows
    scan results with highlighted text, the tells panel, compare, batch, history
    and live model download progress. Set open_browser=true to open it in the
    user's default browser. Never triggers a download."""
    url = dashboard.ensure_started(open_browser=open_browser)
    return {
        "url": url, "dashboard_url": url,
        "port": int(url.rsplit(":", 1)[-1]),
        "default_port": dashboard.default_port(),
        "port_fell_back": int(url.rsplit(":", 1)[-1]) != dashboard.default_port(),
        "history_enabled": history.enabled(),
        "message": f"The ai-detect dashboard is at {url}",
    }


def main():
    threading.Thread(target=_preload_in_background, name="ai-detect-preload", daemon=True).start()
    from .web import app as webapp
    webapp.BEFORE_JOB = _await_ready  # dashboard jobs also wait for the one-thread import
    mcp.run()


if __name__ == "__main__":
    main()
