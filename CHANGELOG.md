# Changelog

## [2.0.0] - 2026-11-24 (prepared, not published)

Previous version: 1.0.0. This is a major version because existing installs are affected: the Python floor rises from 3.9 to 3.11, the MCP server now runs detection in a second process, and `get_model_status` gains states it did not have before. The CLI flags and the five original MCP tool names, parameters and result keys are unchanged.

### Fixed
- **The MCP server hung on Windows.** With a thread blocked reading standard input, loading a C-extension module in another thread never completes. The server imported its ML libraries in a background thread after the stdio loop started, so detect calls waited for ever. Detection now runs in a separate engine process with its standard input closed.
- A fresh install could not start the MCP server: `mcp>=1.0` resolved to SDK 2.x, which removed `mcp.server.fastmcp`. Both SDK lines are now supported and the pin is `mcp>=1.10,<3`.
- Headings and list items with no closing full stop were glued to the next paragraph and scored as one sentence. Text is now parsed into blocks first.
- Sentences were split inside abbreviations ("e.g.", "Dr.").
- Pattern false positives: "it has three ports" flagged as a missing contraction; "features" and "addresses" as nouns flagged as formal verbs.
- Pattern misses: only one inflection and only US spelling were matched ("provide", "leveraging", "utilises" were not); curly apostrophes defeated the phrase list.
- A mistyped file name given as the positional argument was scored as text.
- `--compare` with a missing file raised a traceback; non-UTF-8 files raised `UnicodeDecodeError`.
- An unknown model was only rejected after waiting for the default model to download.

### Added
- A model registry with six detectors: `desklib` (still the default), `light`, `gpttrace-150m`, `gpttrace-1b`, `tabularis`, `conpara`. Each carries its licence, size and RAID rank with source and read date.
- Ensembles: `--model a,b,c` or `--ensemble`, up to five models, each read at its own calibrated operating point.
- Document-level scores (passages of about 200 words) beside the per-sentence scores, and an assessment with a stated confidence.
- URL input (`--url`, MCP `detect_ai_url`, web UI) through headless Chromium. Optional `[web]` extra.
- Structure and style tells: 24 page-level checks, reported separately from model scores.
- Visual tells from the rendered page's geometry, with an annotated screenshot. Optional vision-model second opinion, off by default.
- Optional GPT-2 perplexity and burstiness readout (`--perplexity`).
- A local web UI: `ai-detect serve`. Scan, compare, batch, history, models, export (HTML, CSV, JSON).
- Model downloads in the background with progress, resumable; `ai-detect download <model|all>`; MCP `prefetch`.
- MCP: `detect_ai_url`, `scan_batch`, `prefetch`, `open_dashboard`; server instructions; tool annotations; progress and log notifications; every result carries `dashboard_url`.
- `ai-detect models`, `--batch`, `--export`, `--version`.
- Packaging prepared: npm launcher `@houtini/ai-detect`, `server.json`, MCPB `manifest.json`, release checks.

### Changed
- Python 3.11 or later is required (current torch, transformers and onnxruntime need it).
- `get_model_status` and `list_models` return more fields. `status` keeps the old words (`ready`, `downloading`, `absent`) and adds `failed`; the new `state` field says `not_downloaded` for absent.
- A detect call made while the model is still downloading returns `status: "downloading"` at once instead of waiting.
- The docs no longer call desklib first on RAID. It was when submitted in February 2025; it was 42nd of 61 on 24 Nov 2026.

### Removed
- `scripts/strip_html.py` (HTML input is now built in).

## [1.0.0] - 2026-08

First release: per-sentence detection with desklib and a small ONNX model, pattern diagnostics, CLI and MCP server.
