"""HTTP API and job runner for the local dashboard.

Everything here runs on this machine. The server binds to 127.0.0.1, answers
only requests whose Host header is a loopback name, and makes no outbound call
except: a model download from Hugging Face, the one page the user asks it to
fetch, and (only if the user turns it on) the vision endpoint they configured.
"""

import json
import os
import queue
import tempfile
import threading
import time
import uuid
from importlib import resources

from starlette.applications import Starlette
from starlette.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from starlette.routing import Route

from .. import downloads, history, report as exports
from .._version import __version__
from ..analyze import analyze, compare, load_source
from ..models import DEFAULT_MODEL, MODELS, REGISTRY

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "[::1]", "::1"}
MAX_BODY = 25 * 1024 * 1024
_JOBS = {}
_QUEUE = queue.Queue()
_WORKER = None
_WORKER_LOCK = threading.Lock()
BASE_URL = {"url": ""}  # set by web.server once the real port is known
BEFORE_JOB = None       # set by the MCP server: wait for its one-thread library import


def scan_url(scan_id):
    return f"{BASE_URL['url']}/#/scan/{scan_id}" if BASE_URL["url"] else ""


# ---------------------------------------------------------------------------
# Jobs: one worker thread, so the machine runs one analysis at a time
# ---------------------------------------------------------------------------

def _new_job(kind, fn):
    job = {"id": uuid.uuid4().hex[:12], "kind": kind, "state": "queued", "events": [],
           "progress": {"stage": "queued"}, "result": None, "error": None,
           "created": time.time()}
    _JOBS[job["id"]] = job
    for old in sorted(_JOBS.values(), key=lambda j: j["created"])[:-50]:
        _JOBS.pop(old["id"], None)
    _QUEUE.put((job, fn))
    _ensure_worker()
    return job


def _ensure_worker():
    global _WORKER
    with _WORKER_LOCK:
        if _WORKER is None or not _WORKER.is_alive():
            _WORKER = threading.Thread(target=_work, name="ai-detect-jobs", daemon=True)
            _WORKER.start()


def _work():
    while True:
        job, fn = _QUEUE.get()
        job["state"] = "running"

        def progress(event, job=job):
            job["progress"] = event
            job["events"].append(event)

        try:
            if BEFORE_JOB:
                BEFORE_JOB()
            job["result"] = fn(progress)
            job["state"] = "done"
        except Exception as e:  # reported to the page, never swallowed
            job["error"] = f"{type(e).__name__}: {e}"
            job["state"] = "failed"


def _wait_for_models(model_ids, progress):
    """Download anything missing, reporting progress into the job."""
    while True:
        ready, statuses = downloads.ensure(model_ids)
        failed = [s for s in statuses if s["status"] == "failed"]
        if failed:
            raise RuntimeError(failed[0]["message"])
        if ready:
            return
        progress({"stage": "downloading", "models": statuses})
        time.sleep(0.5)


def run_scan(source, models=None, device=None, perplexity=False, low_memory=False,
             timeout=30.0, progress=None, batch_id=None, label=None):
    """Load, analyse, save. ``source`` is {text|file|url: value}. Returns the report."""
    progress = progress or (lambda event: None)
    model_ids = REGISTRY.parse(models, DEFAULT_MODEL)
    _wait_for_models(model_ids, progress)
    progress({"stage": "fetching" if source.get("url") else "reading"})
    loaded = load_source(timeout=timeout, **source)
    if label:
        loaded.label = label
    report = analyze(loaded, models=model_ids, device=device, perplexity=perplexity,
                     low_memory=low_memory, progress=progress)
    if batch_id:
        report["batch_id"] = batch_id
    scan_id = history.save(report, loaded.screenshot)
    report["dashboard_url"] = scan_url(scan_id)
    return report


def _source_from(body):
    """Pick the one source out of a request body. Uploaded file content is
    written to a private temp file so .html uploads can be rendered."""
    if body.get("url"):
        return {"url": str(body["url"]).strip()}, None
    if body.get("path"):
        return {"file": str(body["path"])}, None
    if body.get("file_content") is not None:
        name = os.path.basename(str(body.get("file_name") or "upload.txt"))
        if name.lower().endswith((".html", ".htm")):
            fd, tmp = tempfile.mkstemp(suffix=".html", prefix="ai-detect-")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(body["file_content"])
            return {"file": tmp}, tmp
        return {"text": body["file_content"]}, None
    text = (body.get("text") or "").strip()
    if not text:
        raise ValueError("Nothing to scan: give text, a URL or a file.")
    return {"text": text}, None


def _options(body):
    return {"models": body.get("models") or None, "device": body.get("device") or None,
            "perplexity": bool(body.get("perplexity")), "low_memory": bool(body.get("low_memory")),
            "timeout": float(body.get("timeout") or 30)}


def _scan_job(body):
    source, tmp = _source_from(body)
    options = _options(body)
    REGISTRY.parse(options["models"], DEFAULT_MODEL)  # reject a bad model id now

    def fn(progress):
        try:
            label = os.path.basename(str(body["file_name"])) if body.get("file_name") else None
            report = run_scan(source, progress=progress, label=label, **options)
            return {"scan_id": report["scan_id"]}
        finally:
            if tmp:
                try:
                    os.remove(tmp)
                except OSError:
                    pass
    return fn


def _compare_job(body):
    options = _options(body)
    sides = []
    for key in ("a", "b"):
        side = body.get(key) or {}
        sides.append(_source_from(side)[0])

    def fn(progress):
        reports = []
        for n, source in enumerate(sides):
            reports.append(run_scan(
                source, progress=lambda e, n=n: progress({**e, "side": "ab"[n]}), **options))
        return {"a": reports[0]["scan_id"], "b": reports[1]["scan_id"],
                "compare": compare(reports[0], reports[1])}
    return fn


def run_batch(items, options, progress=None):
    """Scan many sources one after another. Returns {batch_id, rows}."""
    progress = progress or (lambda event: None)
    batch_id = "b" + uuid.uuid4().hex[:8]
    rows = []
    for n, item in enumerate(items):
        label = item.get("url") or item.get("file") or (item.get("text") or "")[:60]
        row = {"label": label, "error": None}
        try:
            report = run_scan(item, batch_id=batch_id, progress=lambda e, n=n: progress(
                {**e, "item": n, "of": len(items), "rows": rows}), **options)
            row.update(history._summary(report))
            row["label"] = report["source"]["title"] or label
        except Exception as e:
            row["error"] = f"{type(e).__name__}: {e}"
        rows.append(row)
        progress({"stage": "batch", "item": n + 1, "of": len(items), "rows": rows})
    return {"batch_id": batch_id, "rows": rows}


def _batch_job(body):
    items = []
    for raw in body.get("items") or []:
        raw = str(raw).strip()
        if not raw:
            continue
        if raw.lower().startswith(("http://", "https://")):
            items.append({"url": raw})
        else:
            items.append({"file": raw})
    for f in body.get("files") or []:
        items.append({"text": f.get("content", "")})
    if not items:
        raise ValueError("Nothing to scan: give one URL or file path per line.")
    if len(items) > 200:
        raise ValueError("A batch takes at most 200 items.")
    options = _options(body)
    return lambda progress: run_batch(items, options, progress)


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

def _guard(request):
    """Refuse anything not addressed to a loopback name (DNS-rebinding guard)
    and any cross-site write."""
    host = (request.headers.get("host") or "").rsplit(":", 1)[0].lower()
    if host not in LOOPBACK_HOSTS:
        return PlainTextResponse("ai-detect only answers on 127.0.0.1", status_code=403)
    if request.method != "GET":
        origin = request.headers.get("origin")
        if origin and origin.split("//", 1)[-1].rsplit(":", 1)[0].lower() not in LOOPBACK_HOSTS:
            return PlainTextResponse("cross-site request refused", status_code=403)
    return None


async def _body(request):
    raw = await request.body()
    if len(raw) > MAX_BODY:
        raise ValueError("Request too large.")
    return json.loads(raw or b"{}")


def _static(name, media_type):
    data = resources.files("ai_detect").joinpath("web/static/" + name).read_bytes()
    return Response(data, media_type=media_type, headers={"Cache-Control": "no-store"})


def _api(handler):
    async def wrapped(request):
        refused = _guard(request)
        if refused:
            return refused
        try:
            return await handler(request)
        except KeyError as e:
            return JSONResponse({"error": f"Not found: {e}"}, status_code=404)
        except (ValueError, FileNotFoundError) as e:
            return JSONResponse({"error": str(e)}, status_code=400)
    return wrapped


async def index(request):
    return _guard(request) or _static("index.html", "text/html; charset=utf-8")


async def asset(request):
    name = request.path_params["name"]
    kinds = {"app.css": "text/css; charset=utf-8", "app.js": "text/javascript; charset=utf-8"}
    if name not in kinds:
        return PlainTextResponse("not found", status_code=404)
    return _guard(request) or _static(name, kinds[name])


@_api
async def api_state(request):
    return JSONResponse({
        "version": __version__, "default_model": DEFAULT_MODEL,
        "models": [{**spec.public(), **downloads.status(mid)} for mid, spec in MODELS.items()],
        "history": {"enabled": history.enabled(), "folder": history.folder()},
        "url_input": _url_input_available(),
    })


def _url_input_available():
    try:
        import playwright  # noqa: F401
        return True
    except ImportError:
        return False


@_api
async def api_download(request):
    return JSONResponse(downloads.start(request.path_params["model"]))


@_api
async def api_start(request):
    kind = request.path_params["kind"]
    body = await _body(request)
    maker = {"scan": _scan_job, "compare": _compare_job, "batch": _batch_job}[kind]
    job = _new_job(kind, maker(body))
    return JSONResponse({"job_id": job["id"]})


@_api
async def api_job(request):
    job = _JOBS[request.path_params["id"]]
    return JSONResponse({k: job[k] for k in ("id", "kind", "state", "progress", "result", "error")})


@_api
async def api_scans(request):
    if request.method == "DELETE":
        return JSONResponse({"deleted": history.clear()})
    return JSONResponse({"scans": history.list_scans(), "enabled": history.enabled()})


@_api
async def api_scan(request):
    scan_id = request.path_params["id"]
    if request.method == "DELETE":
        history.delete(scan_id)
        return JSONResponse({"deleted": scan_id})
    return JSONResponse(history.load(scan_id))


@_api
async def api_screenshot(request):
    data = history.screenshot(request.path_params["id"])
    if not data:
        return PlainTextResponse("no screenshot", status_code=404)
    return Response(data, media_type="image/jpeg")


@_api
async def api_export(request):
    report = history.load(request.path_params["id"])
    fmt = request.path_params["fmt"]
    name = f"ai-detect-{report['scan_id']}.{fmt}"
    makers = {"json": (exports.to_json, "application/json"),
              "csv": (exports.to_csv, "text/csv; charset=utf-8"),
              "html": (exports.to_html, "text/html; charset=utf-8")}
    if fmt not in makers:
        raise KeyError(fmt)
    make, media = makers[fmt]
    return Response(make(report), media_type=media,
                    headers={"Content-Disposition": f'attachment; filename="{name}"'})


@_api
async def api_batch_csv(request):
    rows = [r for r in history.list_scans() if r.get("batch") == request.path_params["id"]]
    return Response(exports.batch_to_csv(list(reversed(rows))), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": 'attachment; filename="ai-detect-batch.csv"'})


@_api
async def api_settings(request):
    body = await _body(request)
    if "history" in body:
        history.set_enabled(bool(body["history"]))
    return JSONResponse({"history": {"enabled": history.enabled(), "folder": history.folder()}})


@_api
async def api_vision(request):
    """Second opinion from a vision model the user configured. Sends the
    screenshot to that endpoint; refused unless the caller confirms a remote one."""
    from ..visual import is_local_endpoint, vision_review
    body = await _body(request)
    endpoint, model = str(body.get("endpoint") or "").strip(), str(body.get("model") or "").strip()
    if not endpoint or not model:
        raise ValueError("Give the endpoint URL and the model name.")
    if not is_local_endpoint(endpoint) and not body.get("confirm_remote"):
        raise ValueError("That endpoint is not on this machine. Sending would upload the "
                         "screenshot to it. Tick the confirmation to go ahead.")
    scan_id = request.path_params["id"]
    shot = history.screenshot(scan_id)
    try:
        result = vision_review(shot, endpoint, model, api_key=body.get("api_key") or None)
    except RuntimeError as e:
        raise ValueError(str(e)) from e
    return JSONResponse(result)


routes = [
    Route("/", index),
    Route("/static/{name}", asset),
    Route("/api/state", api_state),
    Route("/api/models/{model}/download", api_download, methods=["POST"]),
    Route("/api/start/{kind}", api_start, methods=["POST"]),
    Route("/api/jobs/{id}", api_job),
    Route("/api/scans", api_scans, methods=["GET", "DELETE"]),
    Route("/api/scans/{id}", api_scan, methods=["GET", "DELETE"]),
    Route("/api/scans/{id}/screenshot.jpg", api_screenshot),
    Route("/api/scans/{id}/export.{fmt}", api_export),
    Route("/api/scans/{id}/vision", api_vision, methods=["POST"]),
    Route("/api/batches/{id}/export.csv", api_batch_csv),
    Route("/api/settings", api_settings, methods=["POST"]),
]

app = Starlette(routes=routes)
