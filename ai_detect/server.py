"""MCP server for ai-detect.

Exposes local AI-text detection over the Model Context Protocol (stdio).

Tools
  detect_ai_text    analyse a string
  detect_ai_file    analyse a local file (the engine reads it)
  detect_ai_url     fetch one web page and analyse it
  compare_texts     analyse two texts and report the change
  scan_batch        analyse many files / URLs, one summary row each
  get_model_status  is a model ready, downloading (with progress), absent or failed
  list_models       every model with licence, size, RAID rank and status
  prefetch          start downloading a model now
  open_dashboard    return the local web UI's URL (and open it if asked)

How it is built, and why
------------------------
This process is deliberately thin. It never imports numpy, torch, transformers
or onnxruntime. All detection runs in a second process, the *engine*: the same
local web server that ``ai-detect serve`` starts (ai_detect/web), launched here
as a child with its standard input closed. The tools below are small HTTP
calls to it on 127.0.0.1.

The reason is a Windows behaviour reproduced during the November 2026 rebuild:
while any thread is blocked reading a pipe on standard input (which is what an
MCP stdio server does all day), another thread that loads a C-extension module
hangs until that read returns. The first release imported its ML libraries in
a background thread after the stdio loop had started, so on Windows every
detect call waited forever. Keeping the heavy imports out of the process that
owns stdin removes the problem instead of racing it, and has three useful side
effects: the MCP handshake is immediate, the dashboard and the MCP tools share
one set of loaded models and one download manager, and a crash inside a model
runtime cannot take the MCP connection down.

Nothing blocks on a download. A tool that needs a model that is not on disk
starts the download in the engine and returns at once with
``status: "downloading"``, progress figures, the dashboard URL and one
sentence the client can relay.

Run: ai-detect-mcp   (or: python -m ai_detect.server)
"""

import atexit
import json
import os
import queue
import socket  # noqa: F401  (C extensions are imported now, on the main thread,
import ssl  # noqa: F401      before the stdio reader exists; see the note above)
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser

import anyio
import anyio.to_thread

try:  # MCP Python SDK 2.x
    from mcp.server.mcpserver import Context, MCPServer as _Server
    _LOG_NOTIFICATIONS = False  # SDK 2.x marks the logging capability deprecated (SEP-2577)
except ImportError:  # SDK 1.x
    from mcp.server.fastmcp import Context, FastMCP as _Server
    _LOG_NOTIFICATIONS = True

try:
    from mcp.types import ToolAnnotations
except ImportError:  # pragma: no cover - annotations are optional metadata
    ToolAnnotations = None

from ._version import __version__
from .models import DEFAULT_MODEL, MODELS, REGISTRY
from .web.server import DEFAULT_PORT, default_port

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
    f"The dashboard is at http://127.0.0.1:{DEFAULT_PORT} unless that port was busy; "
    "open_dashboard returns the real address and can open it in the browser.\n"
    "Scores are evidence, not proof. Report the document score with its confidence and "
    "notes; single-sentence scores are a rough signal."
)

mcp = _Server("ai-detect", instructions=INSTRUCTIONS)

ENGINE_START_TIMEOUT = float(os.environ.get("AI_DETECT_READY_TIMEOUT", "60"))
_engine = {"url": "", "process": None, "error": None, "owned": False}
_engine_lock = threading.Lock()


def _annot(**kw):
    return ToolAnnotations(**kw) if ToolAnnotations else None


_READ = dict(readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=False)


# ---------------------------------------------------------------------------
# The engine process
# ---------------------------------------------------------------------------

def _http(url, body=None, method=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"),
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            message = json.loads(e.read()).get("error") or str(e)
        except ValueError:
            message = str(e)
        raise ValueError(message) from None


def _is_engine(url):
    """True only for an ai-detect engine of this package's own version. Another
    release's dashboard on the port (an older install left running, say) has a
    different API and results, so it is not attached to: _start_engine starts
    its own engine instead, which takes the next free port."""
    try:
        state = _http(url + "/api/state", timeout=2)
    except (OSError, ValueError):
        return False
    return isinstance(state, dict) and state.get("version") == __version__


def _spawn_engine(log):
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    return subprocess.Popen(
        [sys.executable, "-m", "ai_detect.cli", "serve", "--no-browser",
         "--exit-with-parent", str(os.getpid())],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=log, creationflags=flags)


def _pump(stream, lines, found):
    """Read the engine's stdout until it closes, on a helper thread. Lines go
    to ``lines`` until ``found`` is set; after that they are read and dropped,
    so the engine can never block on a full pipe. None marks the end."""
    try:
        for raw in iter(stream.readline, b""):
            if not found.is_set():
                lines.put(raw.decode("utf-8", "replace"))
    except (OSError, ValueError):
        pass
    finally:
        lines.put(None)
        try:
            stream.close()
        except OSError:
            pass


def _await_engine(process, timeout):
    """The engine's URL once it answers, or '' if it exits or ``timeout``
    seconds pass first. Never blocks past the deadline on a silent child: the
    pipe is read by _pump, and this thread only waits on a queue."""
    marker = "http://127.0.0.1:"
    lines, found = queue.Queue(), threading.Event()
    threading.Thread(target=_pump, args=(process.stdout, lines, found),
                     name="ai-detect-engine-stdout", daemon=True).start()
    deadline = time.monotonic() + timeout
    url = ""
    try:
        while not url:
            left = deadline - time.monotonic()
            if left <= 0:
                return ""
            try:
                line = lines.get(timeout=min(left, 0.25))
            except queue.Empty:
                continue
            if line is None:  # stdout closed: the engine has exited
                return ""
            if marker in line:
                url = marker + line.split(marker, 1)[1].split()[0]
        while time.monotonic() < deadline:
            if _is_engine(url):
                return url
            if process.poll() is not None:
                return ""
            time.sleep(0.2)
        return ""
    finally:
        found.set()


def _terminate(process):
    if process.poll() is None:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def _start_engine():
    """Find a running ai-detect dashboard of this version on the default port,
    or start one. Returns its URL. Blocking for at most ENGINE_START_TIMEOUT
    seconds (plus one 2-second probe); call from a worker thread."""
    with _engine_lock:
        if _engine["url"] and _is_engine(_engine["url"]):
            return _engine["url"]
        existing = f"http://127.0.0.1:{default_port()}"
        if _is_engine(existing):
            _engine.update(url=existing, owned=False)
            return existing
        log_dir = os.environ.get("AI_DETECT_HOME") or os.path.join(os.path.expanduser("~"), ".ai-detect")
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "engine.log")
        with open(log_path, "ab") as log:  # the child keeps its own handle
            process = _spawn_engine(log)
        _engine.update(process=process, owned=True, url="")
        url = _await_engine(process, ENGINE_START_TIMEOUT)
        if not url:
            code = process.poll()
            _terminate(process)
            _engine.update(process=None, owned=False, url="")
            why = (f"it exited with code {code}" if code is not None
                   else f"it gave no address within {ENGINE_START_TIMEOUT:.0f} seconds and was stopped")
            raise RuntimeError(
                f"ai-detect: the detection engine did not start ({why}). See "
                f"{log_path} for the reason.")
        _engine["url"] = url
        return url


def _stop_engine():
    process = _engine.get("process")
    if process is not None and process.poll() is None:
        process.terminate()


atexit.register(_stop_engine)


async def _call(path, body=None, method=None, timeout=30):
    """One HTTP call to the engine, off the event loop."""
    url = await anyio.to_thread.run_sync(_start_engine)
    return await anyio.to_thread.run_sync(lambda: _http(url + path, body, method, timeout))


async def _models_state(model_ids):
    state = await _call("/api/state")
    by_id = {m["id"]: m for m in state["models"]}
    return [_status_fields(by_id[m]) for m in model_ids]


def _status_fields(m):
    """The status part of one /api/state model row, with the legacy vocabulary."""
    keys = ("label", "approx_mb", "bytes_done", "bytes_total", "percent", "eta_seconds",
            "error", "licence", "runtime", "downloaded", "message")
    state = m["status"]
    return {"model": m["id"], **{k: m.get(k) for k in keys}, "state": state,
            "status": "absent" if state == "not_downloaded" else state, "note": m.get("message")}


async def _ensure_models(model_ids):
    """Start any missing download. Returns None when everything is ready, else
    the immediate "downloading" answer."""
    statuses = await _models_state(model_ids)
    pending = [s for s in statuses if s["state"] != "ready"]
    if not pending:
        return None
    for s in pending:
        if s["state"] != "downloading":
            await _call(f"/api/models/{s['model']}/download", method="POST")
    statuses = await _models_state(model_ids)
    pending = [s for s in statuses if s["state"] != "ready"]
    if not pending:
        return None
    failed = [s for s in pending if s["state"] == "failed"]
    first = (failed or pending)[0]
    url = _engine["url"]
    return {
        "status": "failed" if failed else "downloading",
        "ready": False,
        "models": statuses,
        "dashboard_url": f"{url}/#/models",
        "message": f"{first['message']} Watch progress at {url}/#/models."
                   + ("" if failed else " Ask me again in a minute."),
    }


async def _notify(ctx, progress):
    """Forward engine progress to the client: a progress notification when it
    sent a progressToken (the SDK drops it otherwise), plus a log notification on
    SDK 1.x. SDK 2.x deprecates the logging capability, so none is sent there."""
    if ctx is None:
        return
    stage, model = progress.get("stage", ""), progress.get("model", "")
    index, of = progress.get("index", 0), progress.get("of", 1)
    message = f"{stage} {model}".strip()
    try:
        await ctx.report_progress(index + (0.5 if stage == "scoring" else 0), of, message)
        if _LOG_NOTIFICATIONS:
            await ctx.info(f"ai-detect: {message}")
    except Exception:
        pass  # a client that takes no notifications must not break a scan


async def _run_job(kind, body, ctx=None):
    job_id = (await _call(f"/api/start/{kind}", body))["job_id"]
    last = None
    while True:
        job = await _call(f"/api/jobs/{job_id}")
        if job["state"] == "done":
            return job["result"]
        if job["state"] == "failed":
            raise RuntimeError(job["error"])
        marker = (job["progress"].get("stage"), job["progress"].get("model"))
        if marker != last:
            last = marker
            await _notify(ctx, job["progress"])
        await anyio.sleep(0.3)


def _verdict(pct):
    return "LIKELY AI" if pct > 50 else "LIKELY HUMAN" if pct < 40 else "MIXED"


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
    url = _engine["url"]
    out = {
        "status": "ok",
        "model": data.get("model"),
        "models": data["models"],
        "model_ai_pct": data["model_ai_pct"],
        "verdict": _verdict(data["model_ai_pct"]),
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
        "dashboard_url": f"{url}/#/scan/{data.get('scan_id')}",
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


def _check(model, device):
    """Validate before any work: a typo fails in milliseconds."""
    if device not in (None, "", "auto", "cpu", "cuda", "gpu"):
        raise ValueError(f"Unknown device '{device}'. Use 'auto', 'cpu' or 'cuda'.")
    return REGISTRY.parse(model, DEFAULT_MODEL), (None if device in (None, "", "auto") else device)


async def _detect(source, model, device, include_all_sentences, perplexity, ctx, timeout=30.0):
    model_ids, dev = _check(model, device)
    pending = await _ensure_models(model_ids)
    if pending:
        return pending
    result = await _run_job("scan", {**source, "models": model_ids, "device": dev,
                                     "perplexity": perplexity, "timeout": timeout}, ctx)
    report = await _call("/api/scans/" + result["scan_id"])
    return _summarise(report, include_all_sentences=include_all_sentences), report


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
    if not text or not text.strip():
        raise ValueError("No text provided.")
    out = await _detect({"text": text}, model, device, include_all_sentences, perplexity, ctx)
    return out if isinstance(out, dict) else out[0]


@mcp.tool(annotations=_annot(title="Detect AI text in a file", **_READ))
async def detect_ai_file(
    path: str,
    model: str = DEFAULT_MODEL,
    device: str = "auto",
    include_all_sentences: bool = False,
    perplexity: bool = False,
    ctx: Context = None,
) -> dict:
    """Score a local file (the engine reads it, so a long draft never enters the
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
    out = await _detect({"path": os.path.abspath(path)}, model, device, include_all_sentences,
                        perplexity, ctx)
    if isinstance(out, dict):
        return out
    out[0]["file"] = path
    return out[0]


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

    Public internet addresses only. A URL whose host is, or resolves to, a
    loopback (localhost, 127.0.0.1), private-network (10.x, 172.16-31.x,
    192.168.x), link-local (169.254.x), carrier-grade NAT, multicast, unspecified
    or reserved address is refused with an error, IPv4 and IPv6 alike, and so is
    a redirect or page sub-resource that leads to one. The user can lift this by
    setting AI_DETECT_ALLOW_PRIVATE_URLS=1 in the server's environment (to scan a
    site on their own machine or LAN); it cannot be lifted from a tool call.

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
    parts = urllib.parse.urlparse((url or "").strip())
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"Not a fetchable URL (need http:// or https://): {url!r}")
    out = await _detect({"url": url.strip()}, model, device, include_all_sentences, perplexity,
                        ctx, timeout)
    if isinstance(out, dict):
        return out
    out[0]["url"] = out[1]["source"]["label"]
    return out[0]


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
    model_ids, dev = _check(model, device)
    pending = await _ensure_models(model_ids)
    if pending:
        return pending
    result = await _run_job("compare", {"a": {"text": text_a}, "b": {"text": text_b},
                                        "models": model_ids, "device": dev}, ctx)
    a = await _call("/api/scans/" + result["a"])
    b = await _call("/api/scans/" + result["b"])
    return {
        "status": "ok",
        "a": _summarise(a), "b": _summarise(b),
        "delta_ai_pct": round(a["model_ai_pct"] - b["model_ai_pct"], 1),
        "change": result["compare"],
    }


@mcp.tool(annotations=_annot(title="Scan many files or URLs", readOnlyHint=True,
                             destructiveHint=False, idempotentHint=True, openWorldHint=True))
async def scan_batch(items: list[str], model: str = DEFAULT_MODEL, device: str = "auto",
                     ctx: Context = None) -> dict:
    """Scan up to 200 file paths and/or URLs one after another and return one
    summary row each (verdict, document score, flagged sentences, tells, scan_id).
    Full results open from the dashboard history. May trigger a model download:
    returns status "downloading" at once if the model is not on disk."""
    model_ids, dev = _check(model, device)
    pending = await _ensure_models(model_ids)
    if pending:
        return pending
    result = await _run_job("batch", {"items": items, "models": model_ids, "device": dev}, ctx)
    return {"status": "ok", **result, "dashboard_url": f"{_engine['url']}/#/history"}


@mcp.tool(annotations=_annot(title="Model status", **_READ))
async def get_model_status(model: str = DEFAULT_MODEL) -> dict:
    """Is a model ready, downloading, not downloaded or failed?

    `status` is 'ready', 'downloading', 'absent' or 'failed' (`state` says the
    same with 'not_downloaded' for absent). While downloading it gives bytes_done,
    bytes_total, percent and eta_seconds; after a failure, the reason in `error`.
    `message` is one sentence to relay. Also returns dashboard_url. Never triggers
    a download.
    """
    try:
        model_id = REGISTRY.resolve(model).id
    except ValueError:
        return {"error": f"Unknown model '{model}'", "available": list(MODELS)}
    out = (await _models_state([model_id]))[0]
    out["dashboard_url"] = f"{_engine['url']}/#/models"
    return out


@mcp.tool(annotations=_annot(title="List models", **_READ))
async def list_models() -> dict:
    """List every detection model: size, licence, RAID leaderboard rank (with its
    source and the date it was read), runtime, and download status. Never
    triggers a download."""
    state = await _call("/api/state")
    return {
        "default": DEFAULT_MODEL,
        "max_ensemble": 5,
        "dashboard_url": f"{_engine['url']}/#/models",
        "models": {m["id"]: {**m, **_status_fields(m)} for m in state["models"]},
    }


@mcp.tool(annotations=_annot(title="Download a model", readOnlyHint=False, destructiveHint=False,
                             idempotentHint=True, openWorldHint=True))
async def prefetch(model: str = DEFAULT_MODEL) -> dict:
    """Start downloading a model's weights from Hugging Face in the background so
    the first detection is not delayed. `model` is an id, or 'all'. Returns at
    once with progress; poll get_model_status. A failed or interrupted download
    is resumed by calling this again."""
    ids = list(MODELS) if model == "all" else [REGISTRY.resolve(model).id]
    for model_id in ids:
        await _call(f"/api/models/{model_id}/download", method="POST")
    statuses = await _models_state(ids)
    return {
        "models": statuses,
        "dashboard_url": f"{_engine['url']}/#/models",
        "message": " ".join(s["message"] for s in statuses),
    }


@mcp.tool(annotations=_annot(title="Open the dashboard", readOnlyHint=False,
                             destructiveHint=False, idempotentHint=True, openWorldHint=False))
async def open_dashboard(open_browser: bool = False) -> dict:
    """Return the URL of the local web UI (bound to 127.0.0.1), starting it if
    needed. It shows scan results with highlighted text, the tells panel,
    compare, batch, history and live model download progress. Set
    open_browser=true to open it in the user's default browser. Never triggers
    a download."""
    state = await _call("/api/state")
    url = _engine["url"]
    if open_browser:
        webbrowser.open(url)
    port = int(url.rsplit(":", 1)[-1])
    return {
        "url": url, "dashboard_url": url, "port": port, "default_port": default_port(),
        "port_fell_back": port != default_port(),
        "history_enabled": state["history"]["enabled"], "version": __version__,
        "message": f"The ai-detect dashboard is at {url}",
    }


def main():
    # Start the engine now so it is warm by the first tool call. Only stdlib
    # work happens in this thread; nothing heavy is ever imported here.
    threading.Thread(target=lambda: _safe_start(), name="ai-detect-engine", daemon=True).start()
    mcp.run()


def _safe_start():
    try:
        _start_engine()
    except Exception as e:  # reported again, with the reason, by the first tool call
        _engine["error"] = e


if __name__ == "__main__":
    main()
