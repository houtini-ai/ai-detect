# Changelog

## [2.0.0] - 2026-11-25 (prepared, not published)

Previous version: 1.0.0. This is a major version because existing installs are affected: the default model changes from `desklib` to `gpttrace-150m`, the Python floor rises from 3.9 to 3.11, the MCP server now runs detection in a second process, and `get_model_status` gains states it did not have before. The CLI flags and the five original MCP tool names, parameters and result keys are unchanged.

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
- Code review, 24 Nov 2026:
  - A scan waiting on a model whose download failed restarted the download every half second and never reported the failure. A failed download now stays failed until it is asked for again (Retry, `prefetch`, `ai-detect download`, or the next MCP detect call), and the waiting scan ends with the reason.
  - URL input could be pointed at this machine or the local network, directly or through a redirect. Loopback, private, link-local, carrier-grade NAT, multicast, unspecified and reserved addresses are now refused, for the URL itself and for every request the page makes. `AI_DETECT_ALLOW_PRIVATE_URLS=1` lifts the rule.
  - The MCP server could wait for ever on an engine that started but printed nothing. The start now has a real deadline (`AI_DETECT_READY_TIMEOUT`), after which the engine is stopped and the call fails with the log's path. The engine's output is read for as long as it runs.
  - The MCP server attached to any dashboard on the default port, including another version's. It now attaches only to its own version and otherwise starts its own engine.
  - The URL fetch timeout applied to each step separately, so a fetch could take several times the stated limit. One deadline now covers navigation, settling, scrolling, extraction and the screenshot.
  - The HTML export showed an empty perplexity figure (it read a key that does not exist). It now shows the document and mean perplexity and both burstiness figures.
  - Temp files written for uploaded `.html` content were left behind by Compare, and by Scan when the model id was wrong.
  - On Windows the engine could exit at once, or wait on the wrong handle, when watching for its parent process: the handle functions are now declared with pointer-sized handles, and if the handle cannot be opened the engine polls whether the parent is alive.
  - A progress listener was left registered after every blocking download.
- Found while documenting, 25 Nov 2026:
  - A URL scan printed a Python traceback when Playwright was installed but its driver or Chromium could not start (missing system libraries on a bare Linux image, for example). It now prints the install message, the `playwright install --with-deps chromium` command and the underlying error line.
  - The dashboard's History and Batch tables showed a single-model scan's raw document score beside a verdict taken from the calibrated one. They now show the calibrated score, as the result page does, and mark the raw sentence mean as raw.
  - The dashboard's Compare table read "LIKELY AI" on both sides while the two cards above it read "Likely AI" and "Uncertain". The table now repeats the cards' verdict and calibrated score; the raw rows are labelled raw.
  - A download message could say "about 1 min left" beside `eta_seconds: 6`. Under 45 seconds it now says "less than a minute left", and otherwise the nearest whole minute. The command-line progress bar and the dashboard use the same wording.
  - `scripts/make_screenshots.py` now starts its own dashboard on the default port with a neutral data folder, so no screenshot shows a temp path, a user folder or a fallback port.

### Added
- A model registry with six detectors: `gpttrace-150m` (the default), `gpttrace-1b`, `desklib`, `light`, `tabularis`, `conpara`. Each carries its licence, size and RAID rank with source and read date.
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
- **The default model is `gpttrace-150m`. It was `desklib`.** A bare `ai-detect draft.txt`, an MCP detect call with no `model`, and the dashboard's first scan now use it.
  - Why (figures from `docs/MODEL-EVAL-2026-11.md`, CPU, 24 Nov 2026): the download is 151 MB against 1.74 GB; it scores a sentence in 6.2 ms against 49.8 ms; it is 4th of 61 on RAID against 42nd; 8% of human passages scored over 0.5 against 12%; 3 of 24 casual sentences scored over 0.5 against 17. Its passage AUROC on the local corpus is lower (0.969 against 0.996).
  - Licence: the `gpttrace-150m` weights are CC BY-SA 4.0 (`desklib` is MIT). ai-detect downloads them from the authors' Hugging Face repo and does not redistribute them. Running the model puts no condition on your text, on the results or on ai-detect's MIT code. Attribution and share-alike apply to someone who redistributes or adapts the weights themselves.
  - To keep the old behaviour: `--model desklib` on the command line, `"model": "desklib"` in an MCP call, or tick desklib in the dashboard. `desklib` is unchanged and still supported. Scores from the two models are not comparable with each other.
- ONNX Runtime (`onnxruntime>=1.20`, the CPU build) is now a core dependency, because the default model runs on it. `pip install .` is enough for the default. The `light` and `onnx` extras remain as aliases that add nothing.
- The `gpu-directml` extra installs nothing now. It used to install `onnxruntime-directml`, which cannot share an environment with the core `onnxruntime`: both ship the same package folder, and with both installed the CPU build won (providers were `AzureExecutionProvider` and `CPUExecutionProvider` only, checked 25 Nov 2026). To run the ONNX models on a GPU, replace the build after installing: `pip uninstall -y onnxruntime`, then `pip install --force-reinstall onnxruntime-directml` (Windows) or `onnxruntime-gpu` (NVIDIA CUDA). With no GPU build installed the ONNX models run on the CPU on every platform.
- The npm launcher no longer asks uv for the `light` extra (`AI_DETECT_EXTRAS` still adds extras).
- Compare (`ai-detect --compare`, MCP `compare_texts`, the dashboard): `verdicts` now holds each side's assessment label ("Likely AI", "Uncertain", "Likely human") in place of the 1.0.0 words read from the raw score, and the result gains `calibrated_document_pct`, `delta_calibrated_document_pct`, `operating_point_flagged` and `raw_scale`.
- History and batch rows gain `calibrated_document_pct` and `raw_scale`; the batch CSV gains the same two columns.
- The command line prints an `Assessment:` line (label, calibrated document score, confidence) and marks the single-model sentence mean and document score as raw.
- Python 3.11 or later is required (current torch, transformers and onnxruntime need it).
- `get_model_status` and `list_models` return more fields. `status` keeps the old words (`ready`, `downloading`, `absent`) and adds `failed`; the new `state` field says `not_downloaded` for absent.
- A detect call made while the model is still downloading returns `status: "downloading"` at once instead of waiting.
- The docs no longer call desklib first on RAID. It was when submitted in February 2025; it was 42nd of 61 on 24 Nov 2026.

### Removed
- `scripts/strip_html.py` (HTML input is now built in).

## [1.0.0] - 2026-08

First release: per-sentence detection with desklib and a small ONNX model, pattern diagnostics, CLI and MCP server.
