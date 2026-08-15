<div align="center">
  <img src="https://raw.githubusercontent.com/houtini-ai/ai-detect/main/assets/logo.png" width="120" height="120" alt="ai-detect" />
</div>

# ai-detect - an open source AI detector that runs on your own machine

[![MCP](https://img.shields.io/badge/Model_Context_Protocol-server-8b5cf6?style=flat-square)](https://modelcontextprotocol.io)
[![Model](https://img.shields.io/badge/model-DeBERTa--v3-5b5fff?style=flat-square)](https://huggingface.co/desklib/ai-text-detector-v1.01)
[![Python](https://img.shields.io/badge/python-%E2%89%A53.9-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=flat-square)](https://opensource.org/licenses/MIT)
[![Known Vulnerabilities](https://snyk.io/test/github/houtini-ai/ai-detect/badge.svg)](https://snyk.io/test/github/houtini-ai/ai-detect)

**Is the copy you're buying handwritten? Find out, free and at scale.**

ai-detect is a free, open source AI text detector that runs entirely on your own hardware. It scores writing sentence by sentence using [desklib/ai-text-detector-v1.01](https://huggingface.co/desklib/ai-text-detector-v1.01), a 304-million-parameter DeBERTa-v3-large model that ranked first on the RAID detection benchmark. There is no API key, no per-word pricing and no upload: after a one-off 1.7 GB model download it works offline, on CPU or GPU. It ships as a command-line tool, a Python package and an MCP server, under the MIT licence.

That combination is the point. Every mainstream AI checker - GPTZero, Originality.ai, Copyleaks, Winston - is a hosted service you paste your client's unpublished draft into. This one never sends a byte anywhere.

It isn't Pangram Labs, and no detector is a lie detector - a confident writer who contracts their verbs will sail through. But where there's smoke there's fire, and across a batch of copy the signal is real.

**Quick answers**

| Question | Answer |
|---|---|
| Does it cost anything? | No. MIT licensed, no API key, no usage limits. |
| Does my text leave the machine? | No. Inference is local; the only network call is the first model download. |
| Which model? | DeBERTa-v3-large (304M), RAID benchmark #1. A 126 MB RoBERTa ONNX alternative ships too. |
| Can I self-host it as an API? | It runs as an MCP server (`ai-detect-mcp`) and as an importable Python package. |
| Does it need a GPU? | No. CPU by default; CUDA used automatically when present. |
| How accurate is it? | On paired tests, formal phrasing scored 92.6% AI against 0.03% for the same fact written conversationally. Treat it as a signal across a batch, not a verdict on one sentence. |

## What it tells you

Better than a single percentage, it tells you *why* a line reads as machine-written. The patterns are mapped from 70+ paired sentence tests, formal version against a conversational rewrite of the same information:

- **Missing contractions are the #1 signal.** "The software has been significantly improved" scores 92.6% AI; "software's got a lot better" scores 0.03%.
- **"Provides / offers / delivers" are detector magnets.** So are the **"Furthermore" / "Additionally" / "In conclusion"** openers.
- **"For [group] who [condition]"** framing, vague abstractions where a specific name would do, and, oddly, the word **"noticeably"**.

Each flag comes with a plain-English rewrite suggestion, so the tool doubles as an editing pass. The full pattern write-up is in [`docs/detection-patterns.md`](docs/detection-patterns.md).

```
  Model AI score: 87.1% - LIKELY AI   [desklib]
  Sentences: 3 AI / 0 Human / 3 scored
  SDSL: mean=7.3 words, stddev=1.9, CV=0.26 (very uniform (AI-like))
  Patterns: 1 flaggy adverb, 1 formal verb, 1 formal transition

  >> AI  (0.92) The software has been significantly improved.
              ^ flaggy_adverb: 'significantly' — try 'a lot' or 'massively' or cut it
  >> AI  (0.73) Additionally, the QR2 provides excellent stability.
              ^ formal_verb: 'provides' — try 'gives you' or 'has'
              ^ formal_transition: 'Additionally' — cut it, or use 'And' / 'Plus'
```

## Two detectors

| | `desklib` (default) | `light` (`--model light`) |
|---|---|---|
| Model | DeBERTa-v3-large, 304M | RoBERTa-base int8, ONNX |
| Download | **~1.7 GB**, once | **~126 MB**, once |
| Runtime | PyTorch (CPU or CUDA) | ONNX Runtime (CPU, or GPU via DirectML/CUDA) |
| Best for | the calibrated reference score | a fast, small triage pass |

`desklib` is the one the pattern research was built on and the one I trust for an absolute score. `light` is smaller and quicker to install and it runs hotter — it over-flags a bit — so treat it as a fast first look rather than the final word. Same CLI, same MCP tools, just pass `--model light`.

## Why a local detector rather than a hosted one

The hosted AI checkers - GPTZero, Originality.ai, Copyleaks, Winston AI - all work the same way: you paste the text into their site, their server scores it, you pay per word or per month. For a lot of jobs that's fine. For three, it isn't.

**Client confidentiality.** If you're vetting commissioned copy, that draft is unpublished and often under NDA. Pasting it into a third-party scoring service is a disclosure, whatever the privacy policy says. Running the model locally makes the question moot.

**Volume.** Checking sixty articles from an agency costs nothing here beyond electricity. Per-word pricing turns the same batch into a purchase order.

**Reproducibility.** A hosted model can be retrained on a Tuesday and score your archive differently on Wednesday, with no changelog. A pinned local checkpoint gives you the same number in six months, which matters if the score is going in a report.

The trade is real: you give up a polished dashboard, team accounts and a support contract, and you spend 1.7 GB of disk. As of August 2026 this is beta software and the honest positioning is a signal across a batch, not a verdict you'd take to arbitration.

## Install

```bash
git clone https://github.com/houtini-ai/ai-detect
cd ai-detect
pip install .            # CLI + MCP server (pulls torch, transformers, mcp)
pip install ".[light]"   # add the small ONNX model (onnxruntime)
```

That gives you two commands on your PATH: `ai-detect` (the CLI) and `ai-detect-mcp` (the MCP server). Prefer not to install? `pip install torch transformers` and run `python detect.py ...` from the repo — the old entry point still works.

### Looking for detect.py?

If you came from the article and opened `detect.py` expecting the whole program, you'll have found fourteen lines and assumed something was missing. Nothing is — the file is a shim that keeps `python detect.py ...` working, and the implementation moved into the `ai_detect/` package when this grew past one file:

| File | What's in it |
|------|--------------|
| `ai_detect/detector.py` | Model loading and scoring - both backends live here |
| `ai_detect/patterns.py` | The pattern diagnostics (formal verbs, missing contractions, SDSL) |
| `ai_detect/cli.py` | The command-line interface |
| `ai_detect/server.py` | The MCP server |
| `detect.py` | Backwards-compatible shim - imports and calls `ai_detect.cli` |

Everything is in the repo and nothing is behind a paywall or a gist. Start at `ai_detect/detector.py` if you want to read how the scoring works.

Check your setup any time:

```bash
python scripts/check_env.py
```

## Run it

A CUDA GPU helps but isn't required — it defaults to CPU and uses the GPU automatically if one's there.

```bash
ai-detect --file draft.txt              # score a file
ai-detect --text "your text here"       # score a string
ai-detect --compare a.txt b.txt         # compare two versions
ai-detect --json --file draft.txt       # machine-readable output
ai-detect --model light --file draft.txt   # small/fast model
ai-detect --device cpu --file draft.txt    # force CPU (auto | cpu | cuda)
```

Try it on the bundled examples — one obviously machine-written, one not:

```bash
ai-detect --compare examples/ai-sample.txt examples/human-sample.txt
```

Only the copy-heavy sentences get scored: anything under five words (headings, fragments) is skipped rather than guessed at.

## Use it as an MCP server

`ai-detect` is also a [Model Context Protocol](https://modelcontextprotocol.io) server, so Claude (Desktop, Code, or any MCP client) can run detection for you — including on files, where the server reads the draft so it never has to be pasted into the chat.

Add it to your MCP client config:

```json
{
  "mcpServers": {
    "ai-detect": {
      "command": "ai-detect-mcp"
    }
  }
}
```

If `ai-detect-mcp` isn't on your PATH, use the full Python invocation instead:

```json
{
  "mcpServers": {
    "ai-detect": {
      "command": "python",
      "args": ["-m", "ai_detect.server"],
      "cwd": "C:\\path\\to\\ai-detect"
    }
  }
}
```

Tools it exposes:

| Tool | What it does |
|---|---|
| `detect_ai_text` | Score a string of text, sentence by sentence |
| `detect_ai_file` | Score a local file (server reads it — keeps big drafts out of context) |
| `compare_texts` | Score two texts and report the delta |
| `get_model_status` | Report instantly whether a model is ready, still downloading, or absent |
| `list_models` | List the available models, their sizes, and download state |

## The model & the download

First run of the default model pulls **~1.7 GB** from the Hugging Face Hub and caches it under `~/.cache/huggingface`. After that it's instant and offline. Nothing about your text is sent anywhere — the model runs on your hardware.

> **First run through MCP: the first detect call waits for the download.** The server starts fetching the weights in the background the moment it launches, so the connection itself is never held up — but a detect call issued before that finishes has to wait for it, which can be a few minutes. `get_model_status` returns instantly and distinguishes `ready` / `downloading` / `absent`, so the client can check *before* detecting and tell you what's actually happening rather than looking like it has hung. Claude will typically do this for you; you can also just warm the cache once from the CLI:
>
> ```bash
> ai-detect --text "warming the cache"
> ```
>
> Every call after that, CLI or MCP, is instant. `--model light` (~126 MB) downloads fast enough that it rarely trips this. (The MCP server also spends a few seconds importing its ML libraries at startup — that's expected, and it happens in the background.)
>
> If a download stalls outright, a detect call gives up after 15 minutes with an explanatory error instead of hanging forever. Set `AI_DETECT_READY_TIMEOUT` (seconds, `0` = wait indefinitely) to change that.

Why local and not a hosted API? desklib registers a custom model architecture, so it isn't served by Hugging Face's hosted inference — and even where a hosted detector exists, using it would mean shipping your unpublished copy to someone else's server. For a tool you point at commissioned work, local is the right default. If 1.7 GB is too much, `--model light` is a ~126 MB stand-in.

## Status

Beta, and honest about it. It's a CLI I run on my own commissioned copy: the model does the classification, the pattern diagnostics and rewrite hints are mine. Expect rough edges. If it's useful to you, that's a bonus.

Built by [Houtini](https://houtini.com).
