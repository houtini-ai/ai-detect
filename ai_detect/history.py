"""Local scan history: reports saved as JSON on this machine, nowhere else.

What is saved: every scan run through the dashboard or the MCP server (both go
through ``web.app.run_scan``). The command line does not save: ``ai-detect
draft.txt`` prints its result and writes nothing unless ``--export`` is given.

Default folder: ``~/.ai-detect/history`` (override with AI_DETECT_HOME).
Turn it off with ``AI_DETECT_HISTORY=off`` or ``set_enabled(False)``: scans are
then kept in memory for the life of the process only, so result pages still
open. ``clear()`` deletes everything saved.
"""

import json
import os
import threading
import time
import uuid

MAX_SCANS = 200
_LOCK = threading.Lock()
_MEMORY = {}          # scan id -> (report, screenshot bytes)
_enabled = os.environ.get("AI_DETECT_HISTORY", "on").strip().lower() not in ("off", "0", "false", "no")


def home():
    return os.environ.get("AI_DETECT_HOME") or os.path.join(os.path.expanduser("~"), ".ai-detect")


def folder():
    return os.path.join(home(), "history")


def enabled():
    return _enabled


def set_enabled(value):
    global _enabled
    _enabled = bool(value)


def _path(scan_id, ext="json"):
    if not scan_id.replace("-", "").isalnum():
        raise KeyError(scan_id)
    return os.path.join(folder(), f"{scan_id}.{ext}")


def save(report, screenshot=b""):
    """Store a report and return its scan id (also written into the report)."""
    scan_id = time.strftime("%Y%m%d-%H%M%S-") + uuid.uuid4().hex[:6]
    report["scan_id"] = scan_id
    report["created"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    with _LOCK:
        _MEMORY[scan_id] = (report, screenshot)
        while len(_MEMORY) > MAX_SCANS:
            _MEMORY.pop(next(iter(_MEMORY)))
        if _enabled:
            os.makedirs(folder(), exist_ok=True)
            with open(_path(scan_id), "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False)
            if screenshot:
                with open(_path(scan_id, "jpg"), "wb") as f:
                    f.write(screenshot)
            _prune()
    return scan_id


def _prune():
    names = sorted(n for n in os.listdir(folder()) if n.endswith(".json"))
    for name in names[:-MAX_SCANS]:
        for ext in ("json", "jpg"):
            try:
                os.remove(os.path.join(folder(), name[:-5] + "." + ext))
            except OSError:
                pass


def load(scan_id):
    with _LOCK:
        if scan_id in _MEMORY:
            return _MEMORY[scan_id][0]
    try:
        with open(_path(scan_id), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        raise KeyError(scan_id) from None


def screenshot(scan_id):
    with _LOCK:
        if scan_id in _MEMORY and _MEMORY[scan_id][1]:
            return _MEMORY[scan_id][1]
    try:
        with open(_path(scan_id, "jpg"), "rb") as f:
            return f.read()
    except (OSError, KeyError):
        return b""


def _summary(report):
    a = report.get("assessment", {})
    tells = report.get("tells", {})
    return {
        "scan_id": report.get("scan_id"), "created": report.get("created"),
        "kind": report.get("source", {}).get("kind"),
        "label": report.get("source", {}).get("label"),
        "title": report.get("source", {}).get("title"),
        "models": report.get("models", []),
        "verdict": a.get("label"), "confidence": a.get("confidence"),
        # The figure the result page shows: each model read at its own
        # operating point. document_ai_pct and sentence_ai_pct are raw
        # probabilities when one model ran (raw_scale), calibrated means for
        # an ensemble.
        "calibrated_document_pct": a.get("ai_pct", report.get("document_ai_pct")),
        "document_ai_pct": report.get("document_ai_pct"),
        "sentence_ai_pct": report.get("model_ai_pct"),
        "raw_scale": len(report.get("models", [])) == 1,
        "words": report.get("words"),
        "flagged": report.get("operating_point", {}).get("flagged_sentences"),
        "tells": len(tells.get("structure", [])) + len(tells.get("visual", [])),
        "batch": report.get("batch_id"),
    }


def list_scans():
    """Newest first: one summary row per saved (or in-memory) scan."""
    seen, rows = set(), []
    with _LOCK:
        for scan_id, (report, _shot) in _MEMORY.items():
            seen.add(scan_id)
            rows.append(_summary(report))
    if _enabled and os.path.isdir(folder()):
        for name in os.listdir(folder()):
            if name.endswith(".json") and name[:-5] not in seen:
                try:
                    rows.append(_summary(load(name[:-5])))
                except KeyError:
                    pass
    return sorted(rows, key=lambda r: r["scan_id"] or "", reverse=True)


def delete(scan_id):
    with _LOCK:
        _MEMORY.pop(scan_id, None)
    for ext in ("json", "jpg"):
        try:
            os.remove(_path(scan_id, ext))
        except (OSError, KeyError):
            pass


def clear():
    """Delete every saved scan. Returns how many were removed."""
    with _LOCK:
        n = len(_MEMORY)
        _MEMORY.clear()
    if os.path.isdir(folder()):
        for name in os.listdir(folder()):
            if name.endswith((".json", ".jpg")):
                n += name.endswith(".json")
                try:
                    os.remove(os.path.join(folder(), name))
                except OSError:
                    pass
    return n
