#!/usr/bin/env python3
"""
Command-line interface for ai-detect.

    ai-detect --file draft.txt
    ai-detect --text "Your text here"
    ai-detect --compare a.txt b.txt
    ai-detect --json --file draft.txt
    ai-detect --model light --file draft.txt      # small/fast ONNX model
"""

import argparse
import json
import os
import sys

from .detector import DEFAULT_MODEL, MIN_WORDS, MODELS, classify_text, verdict


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

    pt = data.get("pattern_totals", {})
    if pt:
        parts = [f"{count} {name.replace('_', ' ')}" for name, count in sorted(pt.items(), key=lambda x: -x[1])]
        print(f"  Patterns: {', '.join(parts)}")

    print()

    for r in data["sentences"]:
        label = r["label"]
        s = r["sentence"]
        if len(s) > 110:
            s = s[:107] + "..."

        if label == "Skipped":
            print(f"   --- (skip) {s}")
            continue

        marker = ">> AI " if label == "AI" else "   HUM"
        print(f"  {marker} ({r['confidence']:.2f}) {s}")

        if label == "AI":
            for d in r.get("diagnostics", []):
                print(f"              ^ {d['pattern']}: '{d['match']}' — {d['suggestion']}")

    print()


def _read_source(path_or_text):
    if os.path.isfile(path_or_text):
        with open(path_or_text, "r", encoding="utf-8") as f:
            return f.read()
    return path_or_text


def _force_utf8_output():
    """
    Make stdout/stderr UTF-8 safe.

    The suggestion lines print an em dash ("'significantly' — try 'a lot'").
    On Windows, stdout defaults to the console codepage (cp1252 / cp850), which
    has no U+2014 - so that dash arrives as a replacement character, and on some
    codepages raises UnicodeEncodeError and takes the whole run down. The text
    being analysed is arbitrary user prose, so it can carry anything.

    errors="replace" is the belt-and-braces part: a stray character in someone's
    draft should never be the reason a detection run dies.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                # A redirected or already-detached stream - not worth failing over.
                pass


def main(argv=None):
    _force_utf8_output()

    parser = argparse.ArgumentParser(
        prog="ai-detect",
        description="Per-sentence AI text detection with pattern diagnostics.",
    )
    parser.add_argument("--file", "-f", help="Path to text file")
    parser.add_argument("--text", "-t", help="Text string to analyse")
    parser.add_argument("--compare", "-c", nargs=2, metavar=("FILE1", "FILE2"),
                        help="Compare two files")
    parser.add_argument("--json", "-j", action="store_true", help="JSON output")
    parser.add_argument("--model", "-m", default=DEFAULT_MODEL, choices=list(MODELS),
                        help=f"Detection model (default: {DEFAULT_MODEL}). "
                             "'light' uses a small ONNX model.")
    parser.add_argument("--device", "-d", default=None, choices=["auto", "cpu", "cuda"],
                        help="Compute device (default: auto = GPU if available, else CPU)")
    parser.add_argument("positional", nargs="?", help="File path or text")

    args = parser.parse_args(argv)
    opts = {"model": args.model, "device": args.device}

    if args.compare:
        all_results = []
        for fp in args.compare:
            with open(fp, "r", encoding="utf-8") as f:
                text = f.read()
            data = classify_text(text, **opts)
            if args.json:
                all_results.append({"file": fp, **data})
            else:
                print_results(data, label=os.path.basename(fp))
        if args.json:
            print(json.dumps(all_results, indent=2))
        return 0

    if args.file:
        if not os.path.isfile(args.file):
            print(f"File not found: {args.file}", file=sys.stderr)
            return 1
        text = _read_source(args.file)
    elif args.text:
        text = args.text
    elif args.positional:
        text = _read_source(args.positional)
    else:
        text = sys.stdin.read()

    if not text or not text.strip():
        print("No text provided.", file=sys.stderr)
        return 1

    data = classify_text(text, **opts)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print_results(data)
    return 0


if __name__ == "__main__":
    sys.exit(main())
