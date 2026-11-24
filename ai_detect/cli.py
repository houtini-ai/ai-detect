"""Command-line interface for ai-detect.

    ai-detect --file draft.txt
    ai-detect --text "Your text here"
    ai-detect --url https://example.com/article
    ai-detect --compare a.txt b.txt
    ai-detect --json --file draft.txt
    ai-detect --model light --file draft.txt          # another model
    ai-detect --model gpttrace-150m,light --file d.md # an ensemble
    ai-detect --batch list.txt --export summary.csv   # many files/URLs
    ai-detect serve                                   # the local web UI
    ai-detect download gpttrace-150m                  # fetch a model up front
    ai-detect models                                  # list models and status
"""

import argparse
import json
import os
import sys

from ._version import __version__
from .detector import DEFAULT_MODEL, MIN_WORDS, is_model_cached, verdict
from .models import MODELS, REGISTRY


def print_results(data, label=""):
    if label:
        print(f"\n{'=' * 70}")
        print(f"  {label}")
        print(f"{'=' * 70}")

    ai_pct = data["model_ai_pct"]
    print(f"\n  Model AI score: {ai_pct}% - {verdict(ai_pct)}   [{data.get('model', '')}]")

    skipped = data.get("skipped_count", 0)
    scored = data["ai_count"] + data["human_count"]
    skip_note = f" ({skipped} skipped <{MIN_WORDS} words)" if skipped else ""
    print(f"  Sentences: {data['ai_count']} AI / {data['human_count']} Human / {scored} scored{skip_note}")

    m = data.get("text_metrics", {})
    if m.get("mean"):
        print(f"  SDSL: mean={m['mean']} words, stddev={m['stddev']}, CV={m['cv']} ({m['verdict']})")

    pt = data.get("flagged_pattern_totals", data.get("pattern_totals", {}))
    if pt:
        parts = [f"{count} {name.replace('_', ' ')}" for name, count in sorted(pt.items(), key=lambda x: -x[1])]
        print(f"  Patterns: {', '.join(parts)}")

    if "document_ai_pct" in data and scored:
        a = data.get("assessment", {})
        conf = f", confidence {a['confidence']}" if a.get("confidence") else ""
        print(f"  Document score: {data['document_ai_pct']}% over {len(data['passages'])} "
              f"passage(s), {data.get('words', 0)} words{conf}")
        op = data.get("operating_point")
        if op:
            print(f"  At the 5%-false-positive operating point: {op['flagged_sentences']} of "
                  f"{scored} sentences flagged, document {op['calibrated_document_pct']}%")
        for note in a.get("notes", []):
            print(f"  Note: {note}")
    if data.get("per_model"):
        print("  Per model (raw):")
        for model_id, pm in data["per_model"].items():
            print(f"    {model_id:14} sentences {pm['model_ai_pct']:5.1f}%  document "
                  f"{pm['document_ai_pct']:5.1f}%  flagged {pm['flagged_sentences']}")
    ppl = data.get("perplexity")
    if ppl:
        print(f"  Perplexity (GPT-2): document {ppl['document']}, mean {ppl['mean']}, "
              f"burstiness {ppl['burstiness']}")
    print()

    models = data.get("models", [])
    for r in data["sentences"]:
        label = r["label"]
        s = r["sentence"]
        if len(s) > 110:
            s = s[:107] + "..."

        if label == "Skipped":
            print(f"   --- (skip) {s}")
            continue

        marker = ">> AI " if label == "AI" else "   HUM"
        votes = f" [{r['agreement']}/{len(models)}]" if len(models) > 1 else ""
        print(f"  {marker} ({r['confidence']:.2f}){votes} {s}")

        if label == "AI":
            for d in r.get("diagnostics", []):
                print(f"              ^ {d['pattern']}: '{d['match']}' — {d['suggestion']}")

    print()
    tells = data.get("tells")
    if tells and (tells["structure"] or tells["visual"]):
        print("  Structure and style (separate from the model score):")
        for t in tells["structure"] + tells["visual"]:
            example = f": {t['example'][:70]}" if t["example"] else ""
            print(f"    [{t['severity']:6}] {t['label']}{example}")
            print(f"             -> {t['suggestion']}")
        print()


def _force_utf8_output():
    """Make stdout/stderr UTF-8 safe.

    The suggestion lines print an em dash, and the analysed text is arbitrary
    prose. On Windows stdout defaults to the console codepage, where that can
    raise UnicodeEncodeError and take the whole run down.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass


def _fail(message, code=1):
    print(message, file=sys.stderr)
    return code


def _progress_bar(status):
    width = 28
    filled = int(width * status["percent"] / 100)
    eta = f" {status['eta_seconds'] // 60 + 1} min left" if status.get("eta_seconds") else ""
    sys.stderr.write(f"\r  {status['model']:14} [{'#' * filled}{'.' * (width - filled)}] "
                     f"{status['percent']:5.1f}% of {status['bytes_total'] / 1048576:.0f} MB{eta}   ")
    sys.stderr.flush()


def _download(model_ids):
    """Fetch any missing models with a terminal progress bar. Returns an error
    message, or None when everything is ready."""
    from . import downloads
    for model_id in model_ids:
        if is_model_cached(model_id):
            continue
        spec = REGISTRY.resolve(model_id)
        print(f"Downloading {spec.label} (~{spec.approx_mb} MB, one time; resumes if "
              "interrupted)...", file=sys.stderr)
        try:
            result = downloads.download(model_id, on_progress=_progress_bar)
        except KeyboardInterrupt:
            sys.stderr.write("\n")
            return f"Download of {model_id} interrupted. Run the same command to resume."
        sys.stderr.write("\n")
        if result["status"] != "ready":
            return result["message"]
    return None


def cmd_download(argv):
    ap = argparse.ArgumentParser(prog="ai-detect download",
                                 description="Download model weights ahead of first use.")
    ap.add_argument("model", help="a model id, a comma-separated list, or 'all'")
    args = ap.parse_args(argv)
    try:
        ids = list(MODELS) if args.model == "all" else [REGISTRY.resolve(m).id
                                                        for m in args.model.split(",")]
    except ValueError as e:
        return _fail(str(e), 2)
    error = _download(ids)
    if error:
        return _fail(error)
    for model_id in ids:
        print(f"{model_id}: ready")
    return 0


def cmd_models(argv):
    ap = argparse.ArgumentParser(prog="ai-detect models", description="List detection models.")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args(argv)
    rows = [{**spec.public(), "downloaded": is_model_cached(mid),
             "default": mid == DEFAULT_MODEL} for mid, spec in MODELS.items()]
    if args.json:
        print(json.dumps(rows, indent=2))
        return 0
    print(f"{'model':15} {'size':>8}  {'licence':13} {'RAID rank':11} {'status':15} label")
    for r in rows:
        raid = f"{r['raid']['rank']} of {r['raid']['of']}" if r["raid"] else "-"
        status = "downloaded" if r["downloaded"] else "not downloaded"
        mark = " (default)" if r["default"] else ""
        print(f"{r['id']:15} {r['approx_mb']:>5} MB  {r['licence']:13} {raid:11} {status:15} "
              f"{r['label']}{mark}")
    print("\nRAID rank: TPR at 5% FPR, all attacks, read 2026-11-24 "
          "(https://raid-bench.xyz/leaderboard). Whole documents, not single sentences.")
    return 0


def cmd_serve(argv):
    ap = argparse.ArgumentParser(prog="ai-detect serve",
                                 description="Run the local web UI on 127.0.0.1.")
    ap.add_argument("--port", type=int, default=None,
                    help="port to try first (default 8765, or AI_DETECT_PORT); the next free "
                         "port is used if it is busy")
    ap.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    ap.add_argument("--exit-with-parent", type=int, default=None, metavar="PID",
                    help=argparse.SUPPRESS)  # set by the MCP server that starts this engine
    args = ap.parse_args(argv)
    import threading

    from .detector import preload_dependencies
    from .web.server import serve_forever
    if args.exit_with_parent:
        threading.Thread(target=_exit_when_gone, args=(args.exit_with_parent,), daemon=True).start()
    # Warm the ML libraries in the background so the page is up at once.
    threading.Thread(target=preload_dependencies, name="ai-detect-preload", daemon=True).start()
    serve_forever(port=args.port, open_browser=not args.no_browser)
    return 0


_SYNCHRONIZE = 0x00100000
_PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
_INFINITE = 0xFFFFFFFF
_WAIT_OBJECT_0 = 0
_STILL_ACTIVE = 259
_ERROR_ACCESS_DENIED = 5


def _kernel32():
    """kernel32 with the prototypes declared. Without them ctypes treats every
    argument and result as a C int, which truncates a HANDLE (pointer-sized) on
    64-bit Windows."""
    import ctypes
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    k32.WaitForSingleObject.restype = wintypes.DWORD
    k32.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    k32.GetExitCodeProcess.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    k32.CloseHandle.restype = wintypes.BOOL
    return k32


def _open_process(pid, access):
    """A Windows process handle, or None if it cannot be opened."""
    return _kernel32().OpenProcess(access, False, pid) or None


def _pid_alive(pid):
    """Is a process with this id running? When the answer cannot be had (the
    process belongs to someone else), it is taken to be running."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k32 = _kernel32()
        handle = k32.OpenProcess(_PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ctypes.get_last_error() == _ERROR_ACCESS_DENIED
        try:
            code = wintypes.DWORD()
            if not k32.GetExitCodeProcess(handle, ctypes.byref(code)):
                return True
            return code.value == _STILL_ACTIVE
        finally:
            k32.CloseHandle(handle)
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError:
        return True
    return True


def _wait_until_gone(pid, poll=1.0):
    """Return once process ``pid`` has gone.

    Windows: wait on a handle to it. If the handle cannot be opened (or the
    wait fails), fall back to asking once a ``poll`` whether the pid is still
    alive, instead of treating "cannot open" as "gone".
    Elsewhere: ``pid`` is this process's parent; it has gone when we are
    re-parented."""
    import time
    if os.name != "nt":
        while os.getppid() == pid:
            time.sleep(poll)
        return
    handle = _open_process(pid, _SYNCHRONIZE)
    if handle:
        k32 = _kernel32()
        try:
            if k32.WaitForSingleObject(handle, _INFINITE) == _WAIT_OBJECT_0:
                return
        finally:
            k32.CloseHandle(handle)
    while _pid_alive(pid):
        time.sleep(poll)


def _exit_when_gone(pid):
    """Stop this process when the process that started it has gone, so an MCP
    client that is killed does not leave an engine behind."""
    _wait_until_gone(pid)
    os._exit(0)


def _looks_like_path(value):
    return (" " not in value.strip() and "\n" not in value
            and (os.sep in value or "/" in value or os.path.splitext(value)[1] != ""))


def _export(path, report_or_rows):
    from . import report as exports
    ext = os.path.splitext(path)[1].lower()
    if isinstance(report_or_rows, list):
        text = exports.batch_to_csv(report_or_rows) if ext == ".csv" else json.dumps(report_or_rows, indent=2)
    else:
        makers = {".html": exports.to_html, ".htm": exports.to_html, ".csv": exports.to_csv,
                  ".json": exports.to_json}
        if ext not in makers:
            raise ValueError("--export needs a .html, .csv or .json file name")
        text = makers[ext](report_or_rows)
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)
    print(f"Wrote {path}", file=sys.stderr)


def main(argv=None):
    _force_utf8_output()
    argv = list(sys.argv[1:] if argv is None else argv)
    commands = {"serve": cmd_serve, "download": cmd_download, "models": cmd_models}
    if argv and argv[0] in commands:
        return commands[argv[0]](argv[1:])

    parser = argparse.ArgumentParser(
        prog="ai-detect",
        description="Local AI text detection: per-sentence and per-document scores, pattern "
                    "diagnostics, structure and style tells.",
        epilog="Other commands: ai-detect serve | ai-detect download <model|all> | ai-detect models",
    )
    parser.add_argument("--file", "-f", help="Path to a text, Markdown or HTML file")
    parser.add_argument("--text", "-t", help="Text string to analyse")
    parser.add_argument("--url", "-u", help="One web page to fetch and analyse (needs the [web] extra)")
    parser.add_argument("--compare", "-c", nargs=2, metavar=("A", "B"),
                        help="Compare two files or URLs")
    parser.add_argument("--batch", "-b", metavar="LIST",
                        help="A text file with one path or URL per line; scan them all")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--model", "-m", default=None, metavar="ID[,ID...]",
                        help=f"Model id, or up to 5 comma-separated ids to run as an ensemble "
                             f"(default: {DEFAULT_MODEL}). Choices: {', '.join(MODELS)}")
    parser.add_argument("--ensemble", "-e", action="store_true",
                        help="Run every downloaded model (up to 5) as an ensemble")
    parser.add_argument("--device", "-d", default=None, choices=["auto", "cpu", "cuda"],
                        help="Compute device (default: auto = GPU if available, else CPU)")
    parser.add_argument("--perplexity", "-p", action="store_true",
                        help="Add GPT-2 perplexity and burstiness (548 MB on first use)")
    parser.add_argument("--no-tells", action="store_true",
                        help="Skip the structure and style tells")
    parser.add_argument("--low-memory", action="store_true",
                        help="With an ensemble: load and unload models one at a time")
    parser.add_argument("--timeout", type=float, default=30.0,
                        help="Seconds to wait for a URL (default 30)")
    parser.add_argument("--export", "-o", metavar="PATH",
                        help="Also write the report to PATH (.html, .csv or .json)")
    parser.add_argument("--version", "-V", action="version", version=f"ai-detect {__version__}")
    parser.add_argument("positional", nargs="?", help="File path, URL or text")

    args = parser.parse_args(argv)
    try:
        if args.ensemble:
            model_ids = [m for m in MODELS if is_model_cached(m)][:5]
            if len(model_ids) < 2:
                return _fail("--ensemble needs at least two downloaded models. "
                             "Fetch some with: ai-detect download <model>", 2)
        else:
            model_ids = REGISTRY.parse(args.model, DEFAULT_MODEL)
    except ValueError as e:
        return _fail(str(e), 2)

    from .analyze import analyze, compare, load_source
    from .backends import MissingRuntimeError
    from .fetch import UrlFetchError, UrlFetchUnavailable, is_url

    def source_for(value):
        if is_url(value):
            return {"url": value}
        return {"file": value}

    def run(source):
        loaded = load_source(timeout=args.timeout, **source)
        return analyze(loaded, models=model_ids, device=args.device, perplexity=args.perplexity,
                       tells=not args.no_tells, low_memory=args.low_memory)

    try:
        error = _download(model_ids)
        if error:
            return _fail(error)

        if args.compare:
            reports = [run(source_for(v)) for v in args.compare]
            if args.json:
                print(json.dumps([{"file": v, **r} for v, r in zip(args.compare, reports)], indent=2))
            else:
                for v, r in zip(args.compare, reports):
                    print_results(r, label=os.path.basename(v) if not is_url(v) else v)
                c = compare(*reports)
                print(f"  Change, {args.compare[0]} -> {args.compare[1]}: sentence score "
                      f"{c['sentence_ai_pct'][0]}% -> {c['sentence_ai_pct'][1]}%, document "
                      f"{c['document_ai_pct'][0]}% -> {c['document_ai_pct'][1]}%, patterns "
                      f"{c['patterns'][0]} -> {c['patterns'][1]}, tells {c['tells'][0]} -> {c['tells'][1]}\n")
            return 0

        if args.batch:
            from .analyze import read_text_file
            items = [ln.strip() for ln in read_text_file(args.batch).splitlines()
                     if ln.strip() and not ln.startswith("#")]
            rows = []
            for n, item in enumerate(items, 1):
                row = {"label": item, "error": None}
                try:
                    r = run(source_for(item))
                    a = r["assessment"]
                    row.update(verdict=a["label"], confidence=a["confidence"],
                               document_ai_pct=r["document_ai_pct"], sentence_ai_pct=r["model_ai_pct"],
                               words=r["words"], flagged=r["operating_point"]["flagged_sentences"],
                               tells=len(r["tells"]["structure"]) + len(r["tells"]["visual"]))
                except (OSError, ValueError, UrlFetchError) as e:
                    row["error"] = str(e)
                rows.append(row)
                print(f"  [{n}/{len(items)}] {item}: "
                      f"{row['error'] or row['verdict'] + ', document ' + str(row['document_ai_pct']) + '%'}",
                      file=sys.stderr)
            if args.export:
                _export(args.export, rows)
            if args.json:
                print(json.dumps(rows, indent=2))
            else:
                print(f"\n  {'document':>9} {'sentences':>10} {'flagged':>8} {'tells':>6}  verdict        source")
                for row in rows:
                    if row["error"]:
                        print(f"  {'':>9} {'':>10} {'':>8} {'':>6}  ERROR          {row['label']}: {row['error']}")
                    else:
                        print(f"  {row['document_ai_pct']:>8}% {row['sentence_ai_pct']:>9}% "
                              f"{row['flagged']:>8} {row['tells']:>6}  {row['verdict']:14} {row['label']}")
                print()
            return 0

        if args.url:
            source = {"url": args.url}
        elif args.file:
            source = {"file": args.file}
        elif args.text:
            source = {"text": args.text}
        elif args.positional:
            if is_url(args.positional) or os.path.isfile(args.positional):
                source = source_for(args.positional)
            elif _looks_like_path(args.positional):
                return _fail(f"File not found: {args.positional}")
            else:
                source = {"text": args.positional}
        else:
            source = {"text": sys.stdin.read()}
        if not any(str(v).strip() for v in source.values()):
            return _fail("No text provided.")

        data = run(source)
        if args.export:
            _export(args.export, data)
        if args.json:
            print(json.dumps(data, indent=2))
        else:
            print_results(data)
        return 0
    except FileNotFoundError as e:
        return _fail(str(e) if str(e).startswith("No such file") else f"File not found: {e.filename or e}")
    except (UrlFetchUnavailable, UrlFetchError, MissingRuntimeError, ValueError) as e:
        return _fail(str(e))


if __name__ == "__main__":
    sys.exit(main())
