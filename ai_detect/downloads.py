"""Model downloads that never look like a hang: background, with progress.

One process-wide manager tracks every model in the registry:

    not_downloaded -> downloading (bytes done / total, percent, ETA) -> ready
                                \\-> failed (with the reason; call start() to retry)

A failed download stays failed until someone asks for it again: ``start()``
(the dashboard's Retry button, the MCP prefetch tool and detect tools, the
``ai-detect download`` command) retries it, ``ensure()`` never does. A job
that is waiting on a model therefore sees the failure and reports its reason
instead of restarting the download on every poll.

``start(model)`` returns at once and downloads in a daemon thread.
``download(model)`` blocks and reports through a callback (the CLI's progress
bar). Downloads resume: huggingface_hub keeps partial files and continues from
where they stopped, so a retry after a failure or Ctrl-C does not start over.
"""

import threading
import time

from .detector import is_model_cached
from .models import MODELS, REGISTRY

_LOCK = threading.Lock()
_STATE = {}       # model id -> dict
_THREADS = {}
_LISTENERS = []   # callables(status dict), called on every progress tick


def _blank(model_id):
    return {"model": model_id, "state": "unknown", "bytes_done": 0, "bytes_total": 0,
            "started": None, "error": None, "updated": 0.0}


def subscribe(listener):
    _LISTENERS.append(listener)


def unsubscribe(listener):
    try:
        _LISTENERS.remove(listener)
    except ValueError:
        pass


def _notify(model_id):
    snapshot = status(model_id)
    for listener in list(_LISTENERS):
        try:
            listener(snapshot)
        except Exception:
            pass


def _human(n):
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.0f} {unit}" if unit in ("B", "KB") else f"{n:.1f} {unit}"
        n /= 1024


def status(model):
    """The download state of one model, as a plain dict safe to return to a client.

    state: 'ready' | 'downloading' | 'not_downloaded' | 'failed'
    """
    spec = REGISTRY.resolve(model)
    with _LOCK:
        st = dict(_STATE.get(spec.id) or _blank(spec.id))
    if st["state"] == "failed" and is_model_cached(spec.id):
        # Fetched some other way since (the CLI in another process, say): the
        # old failure no longer describes anything.
        st.update(state="ready", error=None)
    if st["state"] not in ("downloading", "failed"):
        st["state"] = "ready" if is_model_cached(spec.id) else "not_downloaded"
    total = st["bytes_total"] or spec.approx_mb * 1024 * 1024
    done = total if st["state"] == "ready" else st["bytes_done"]
    percent = round(min(100.0, done * 100 / total), 1) if total else 0.0
    eta = None
    if st["state"] == "downloading" and st["started"] and done > 0:
        rate = done / max(0.5, time.time() - st["started"])
        eta = int((total - done) / rate) if rate > 0 else None
    out = {
        "model": spec.id, "label": spec.label, "status": st["state"],
        "downloaded": st["state"] == "ready", "approx_mb": spec.approx_mb,
        "bytes_done": int(done), "bytes_total": int(total), "percent": percent,
        "eta_seconds": eta, "error": st["error"],
        "licence": spec.licence, "runtime": spec.runtime,
    }
    size = _human(total)
    if st["state"] == "ready":
        out["message"] = f"{spec.id} is downloaded and ready."
    elif st["state"] == "downloading":
        left = f", about {eta // 60 + 1} min left" if eta else ""
        out["message"] = f"Downloading {spec.id} ({size}): {percent:.0f}%{left}."
    elif st["state"] == "failed":
        out["message"] = (f"The {spec.id} download failed: {st['error']}. It can be retried "
                          "and will resume from where it stopped: use Retry on the dashboard's "
                          f"Models page, the prefetch tool, or `ai-detect download {spec.id}`.")
    else:
        out["message"] = (f"{spec.id} is not downloaded yet ({size}, one time). It downloads "
                          "on first use, or fetch it now with the prefetch tool or "
                          f"`ai-detect download {spec.id}`.")
    return out


def all_status():
    return {model_id: status(model_id) for model_id in MODELS}


def _file_plan(spec):
    """[(repo, filename, size, cached)] for everything the model needs."""
    from huggingface_hub import snapshot_download
    plan = []
    for repo, patterns in ((spec.repo, spec.files), *spec.extra_repos):
        for info in snapshot_download(repo, allow_patterns=list(patterns), dry_run=True,
                                      tqdm_class=_silent_tqdm()):
            plan.append((repo, info.filename, int(info.file_size or 0), bool(info.is_cached)))
    return plan


def _silent_tqdm():
    from tqdm.auto import tqdm

    class Silent(tqdm):
        def __init__(self, *args, **kwargs):
            kwargs["disable"] = True
            super().__init__(*args, **kwargs)
    return Silent


def _progress_class(model_id):
    from tqdm.auto import tqdm

    class Progress(tqdm):
        def __init__(self, *args, **kwargs):
            kwargs["disable"] = True  # no terminal output; we report ourselves
            super().__init__(*args, **kwargs)
            # A resumed file starts part-way through: count what is already there.
            self._count(getattr(self, "n", 0) or kwargs.get("initial", 0) or 0)

        def _count(self, n):
            if n and getattr(self, "unit", "B") == "B":
                with _LOCK:
                    st = _STATE[model_id]
                    st["bytes_done"] += n
                    tick = time.time() - st["updated"] > 0.25
                    if tick:
                        st["updated"] = time.time()
                if tick:
                    _notify(model_id)

        def update(self, n=1):
            self._count(n)
            return super().update(n)

    return Progress


def download(model, on_progress=None):
    """Download a model's files, blocking. Returns the final status dict.
    Raises nothing: a failure is recorded and returned with status 'failed'."""
    spec = REGISTRY.resolve(model)
    def listener(s):
        if s["model"] == spec.id:
            on_progress(s)

    if on_progress:
        subscribe(listener)
    try:
        return _download(spec)
    finally:
        unsubscribe(listener)


def _download(spec):
    with _LOCK:
        _STATE[spec.id] = {**_blank(spec.id), "state": "downloading", "started": time.time()}
    try:
        from huggingface_hub import hf_hub_download
        plan = _file_plan(spec)
        with _LOCK:
            st = _STATE[spec.id]
            st["bytes_total"] = sum(size for _, _, size, _ in plan)
            st["bytes_done"] = sum(size for _, _, size, cached in plan if cached)
        _notify(spec.id)
        progress = _progress_class(spec.id)
        for repo, filename, _size, cached in plan:
            if not cached:
                hf_hub_download(repo, filename=filename, tqdm_class=progress)
        with _LOCK:
            _STATE[spec.id] = {**_blank(spec.id), "state": "ready"}
    except BaseException as e:  # includes KeyboardInterrupt: record it, then re-raise
        with _LOCK:
            st = _STATE.get(spec.id) or _blank(spec.id)
            st.update(state="failed", error=f"{type(e).__name__}: {e}"[:300] or "interrupted")
            _STATE[spec.id] = st
        _notify(spec.id)
        if not isinstance(e, Exception):
            raise
    _notify(spec.id)
    return status(spec.id)


def start(model):
    """Begin a background download if one is needed. Returns status at once.
    This is the explicit request: it also retries a download that failed."""
    spec = REGISTRY.resolve(model)
    if is_model_cached(spec.id):
        return status(spec.id)
    with _LOCK:
        thread = _THREADS.get(spec.id)
        if thread is None or not thread.is_alive():
            _STATE[spec.id] = {**_blank(spec.id), "state": "downloading", "started": time.time()}
            thread = threading.Thread(target=download, args=(spec.id,),
                                      name=f"ai-detect-download-{spec.id}", daemon=True)
            _THREADS[spec.id] = thread
            thread.start()
    return status(spec.id)


def ensure(models):
    """For a list of model ids: start any missing download and return
    (all_ready, [status, ...]).

    A model whose last download failed is NOT started again: its status comes
    back as 'failed' with the reason, so a caller polling this sees the failure.
    Only start() retries."""
    statuses = []
    for model in models:
        current = status(model)
        statuses.append(current if current["status"] == "failed" else start(model))
    return all(s["status"] == "ready" for s in statuses), statuses
