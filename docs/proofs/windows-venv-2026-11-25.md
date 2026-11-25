# Proof: install, first run and the full-path MCP command on Windows, 25 Nov 2026

Run on 25 Nov 2026 on Windows 11 Pro, Python 3.13.2, Node 24.6.0, in PowerShell 7. The code was a `git bundle` of the unpushed branch `rebuild-2026-11` (commit 84bfef3), cloned into a new folder outside the repository, under a user folder whose name contains a space. A new virtual environment was made inside the clone. `HF_HOME` pointed at an empty folder, so the model really was downloaded. The user-folder name is replaced by `<user>` throughout. The folder was deleted afterwards.

## Results

| # | Step | Result |
|---|---|---|
| 1 | `python -m venv .venv`, activate, `pip install .` (no extras) | Works. 75 s. torch 2.15.0+cpu, onnxruntime 1.32.0, transformers 5.24.1, mcp 2.3.0. The venv is 938 MB |
| 2 | `ai-detect --version` | `ai-detect 2.0.0` |
| 3 | A bare `ai-detect ..\sample.txt` (no `--model`) | Downloads `gpttrace-150m` (148 MB on disk) and scores it on `CPUExecutionProvider`. 33 s including the download. Nothing was written to `AI_DETECT_HOME` |
| 4 | Providers in a plain install | `['AzureExecutionProvider', 'CPUExecutionProvider']`; `torch.cuda.is_available()` is `False` (the PyPI wheel for Windows is CPU-only), on a machine that has two NVIDIA GPUs |
| 5 | The MCP server started by its full path, venv not activated: `...\.venv\Scripts\ai-detect-mcp.exe`, driven by `scripts/smoke_mcp.mjs` | `initialize` ok (ai-detect 2.0.0), 9 tools listed, one scan with the default model, `SMOKE PASS`. 6 s. The scan was saved to history (an MCP scan is) |
| 6 | The same path written into a JSON config with doubled backslashes, parsed, and the parsed command started | `SMOKE PASS`. With single backslashes the file is not valid JSON |

The config that worked:

```json
{
  "mcpServers": {
    "ai-detect": {
      "command": "C:\\Users\\<user>\\ai-detect-proof\\ai-detect\\.venv\\Scripts\\ai-detect-mcp.exe"
    }
  }
}
```

What this does not show: the config was not loaded into Claude Desktop. The smoke script starts the command the way an MCP client does (the command alone, no shell, standard input and output as pipes).

Two things in the transcript that a reader will also see: huggingface_hub warns that requests are unauthenticated, and warns once that the cache cannot use symlinks on Windows without Developer Mode. Neither stops the download.

## Transcript 1: clone, venv, install, first scan, MCP by full path

```text
== machine

PS> python --version
Python 3.13.2
[exit 0, 0 s]

PS> (Get-CimInstance Win32_OperatingSystem).Caption
Microsoft Windows 11 Pro
[exit 0, 0 s]

PS> git clone -q -b rebuild-2026-11 $Bundle ai-detect
[exit 0, 1 s]

PS> git log --oneline -1
84bfef3 feat: default model is gpttrace-150m; onnxruntime is a core dependency; five fixes found while documenting
[exit 0, 0 s]

== a fresh virtual environment, no extras

PS> python -m venv .venv
[exit 0, 4 s]

PS> .\.venv\Scripts\Activate.ps1
[exit 0, 0 s]

PS> python -c "import sys; print(sys.prefix)"
C:\Users\<user>\ai-detect-proof\ai-detect\.venv
[exit 0, 0 s]

PS> pip install . | Select-Object -Last 6
  Building wheel for ai-detect (pyproject.toml): finished with status 'done'
  Created wheel for ai-detect: filename=ai_detect-2.0.0-py3-none-any.whl size=140850 sha256=459d7dad4aa07b9278f04727dd57e391f7d017e1e77508bdaaf04dfe9e1d8e77
  Stored in directory: C:\Users\<user>\appdata\local\pip\cache\wheels\2c\69\4b\d04508c6e94f9a8f13950b167d2d0f5481ecbf76b998da74fc
Successfully built ai-detect
Installing collected packages: mpmath, flatbuffers, typing_extensions, truststore, sympy, shellingham, setuptools, safetensors, rpds-py, regex, pyyaml, pywin32, python-multipart, pyjwt, pygments, pycparser, protobuf, packaging, numpy, networkx, mdurl, MarkupSafe, idna, hf-xet, h11, fsspec, filelock, colorama, click, attrs, annotated-types, annotated-doc, uvicorn, typing-inspection, tqdm, referencing, pydantic-core, opentelemetry-api, onnxruntime, markdown-it-py, jinja2, httpcore2, cffi, anyio, torch, starlette, rich, pydantic, jsonschema-specifications, httpx2, cryptography, typer, sse-starlette, mcp-types, jsonschema, huggingface-hub, tokenizers, mcp, transformers, ai-detect
Successfully installed MarkupSafe-3.0.4 ai-detect-2.0.0 annotated-doc-0.0.7 annotated-types-0.8.0 anyio-4.16.0 attrs-26.1.0 cffi-2.1.1 click-8.5.1 colorama-0.4.6 cryptography-50.0.2 filelock-4.3.1 flatbuffers-25.12.19 fsspec-2026.9.0 h11-0.16.0 hf-xet-1.8.0 httpcore2-2.16.2 httpx2-2.16.2 huggingface-hub-2.4.0 idna-3.20 jinja2-3.1.6 jsonschema-4.26.0 jsonschema-specifications-2025.9.1 markdown-it-py-4.3.0 mcp-2.3.0 mcp-types-2.3.0 mdurl-0.1.2 mpmath-1.3.0 networkx-3.7 numpy-2.5.5 onnxruntime-1.32.0 opentelemetry-api-1.45.2 packaging-26.4 protobuf-7.36.2 pycparser-3.12 pydantic-2.14.4 pydantic-core-2.50.5 pygments-2.21.0 pyjwt-2.15.1 python-multipart-0.0.34 pywin32-312 pyyaml-6.0.4 referencing-0.37.0 regex-2026.11.24 rich-15.0.0 rpds-py-2026.9.1 safetensors-0.8.0 setuptools-84.2.1 shellingham-1.5.4 sse-starlette-3.7.1 starlette-1.10.0 sympy-1.14.0 tokenizers-0.23.3 torch-2.15.0 tqdm-4.70.1 transformers-5.24.1 truststore-0.10.5 typer-0.29.2 typing-inspection-0.4.5 typing_extensions-4.16.0 uvicorn-0.54.0
[exit 0, 75 s]

PS> pip list | Select-String -Pattern "^(ai-detect|torch|onnxruntime|transformers|tokenizers|huggingface|mcp|numpy|playwright)"
ai-detect                 2.0.0
huggingface_hub           2.4.0
mcp                       2.3.0
mcp-types                 2.3.0
numpy                     2.5.5
onnxruntime               1.32.0
tokenizers                0.23.3
torch                     2.15.0
transformers              5.24.1
[exit 0, 3 s]

PS> "{0:n0} MB" -f ((Get-ChildItem .venv -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
938 MB
[exit 0, 1 s]

PS> ai-detect --version
ai-detect 2.0.0
[exit 0, 1 s]

PS> ai-detect models
model               size  licence       RAID rank   status          label
desklib          1736 MB  MIT           42 of 61    not downloaded  desklib/ai-text-detector-v1.01 (DeBERTa-v3-large)
light             126 MB  MIT           36 of 61    not downloaded  TMR ai-text-detector (RoBERTa-base, int8 ONNX)
gpttrace-150m     151 MB  CC-BY-SA-4.0  4 of 61     not downloaded  GPTTrace Ettin-150M v5e (int8 ONNX) (default)
gpttrace-1b       951 MB  CC-BY-SA-4.0  2 of 61     not downloaded  GPTTrace Ettin-1B v8s (4-bit ONNX)
tabularis         598 MB  MIT           21 of 61    not downloaded  Tabularis ModernBERT R1.1
conpara          1738 MB  MIT           20 of 61    not downloaded  DeBERTa-ConPara (DeBERTa-v3-large)

RAID rank: TPR at 5% FPR, all attacks, read 2026-11-24 (https://raid-bench.xyz/leaderboard). Whole documents, not single sentences.
[exit 0, 0 s]

== first scan: bare ai-detect sample.txt (no --model): downloads the default

PS> ai-detect ..\sample.txt
Downloading GPTTrace Ettin-150M v5e (int8 ONNX) (~151 MB, one time; resumes if interrupted)...
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.

  gpttrace-150m  [............................]   0.0% of 148 MB   
  gpttrace-150m  [............................]   2.3% of 148 MB about 1 min left   C:\Users\<user>\ai-detect-proof\ai-detect\.venv\Lib\site-packages\huggingface_hub\file_download.py:149: UserWarning: `huggingface_hub` cache-system uses symlinks by default to efficiently store duplicated files but your machine does not support them in C:\Users\<user>\ai-detect-proof\hf-cache\hub\models--nakas--gpttrace-ettin150-text-v5e. Caching files will still work but in a degraded version that might require more space on your disk. This warning can be disabled by setting the `HF_HUB_DISABLE_SYMLINKS_WARNING` environment variable. For more details, see https://huggingface.co/docs/huggingface_hub/how-to-cache#limitations.
To support symlinks on Windows, you either need to activate Developer Mode or to run Python as an administrator. In order to activate developer mode, see this article: https://docs.microsoft.com/en-us/windows/apps/get-started/enable-your-device-for-development
  warnings.warn(message)
C:\Users\<user>\ai-detect-proof\ai-detect\.venv\Lib\site-packages\huggingface_hub\file_download.py:149: UserWarning: `huggingface_hub` cache-system uses symlinks by default to efficiently store duplicated files but your machine does not support them in C:\Users\<user>\ai-detect-proof\hf-cache\hub. Caching files will still work but in a degraded version that might require more space on your disk. This warning can be disabled by setting the `HF_HUB_DISABLE_SYMLINKS_WARNING` environment variable. For more details, see https://huggingface.co/docs/huggingface_hub/how-to-cache#limitations.
To support symlinks on Windows, you either need to activate Developer Mode or to run Python as an administrator. In order to activate developer mode, see this article: https://docs.microsoft.com/en-us/windows/apps/get-started/enable-your-device-for-development
  warnings.warn(message)

  gpttrace-150m  [............................]   2.4% of 148 MB about 2 min left   
  gpttrace-150m  [............................]   3.2% of 148 MB about 2 min left   
  ... (64 more progress lines, not shown)
  gpttrace-150m  [##..........................]   9.5% of 148 MB less than a minute left   
  gpttrace-150m  [############################] 100.0% of 151 MB   
Loading GPTTrace Ettin-150M v5e (int8 ONNX) (ONNX)...
Model loaded via onnxruntime CPUExecutionProvider (GPTTrace Ettin-150M v5e (int8 ONNX))

  Model AI score (raw mean of sentences): 63.4% - LIKELY AI   [gpttrace-150m]
  Assessment: Uncertain (calibrated document score 54.1%, confidence low)
  Sentences: 2 AI / 2 Human / 4 scored
  SDSL: mean=18.0 words, stddev=4.9, CV=0.27 (very uniform (AI-like))
  Patterns: 3 formal verb, 3 ai slop, 2 formal transition, 1 vague abstraction
  Document score (raw): 82.9% over 1 passage(s), 72 words, confidence low
  At the 5%-false-positive operating point: 2 of 4 sentences flagged, document 54.1%
  Note: Only 72 words. The model cards call results under about 150 words unreliable.
  Note: Sentence scores are split, which can mean mixed authorship or an edited draft. Single-sentence scores are a rough signal.

  >> AI  (1.00) Furthermore, the platform provides a seamless experience for modern teams, and it offers comprehensive supp...
              ^ formal_verb: 'provides': try 'gives you' or 'has'
              ^ formal_verb: 'offers': try 'has' or 'comes with'
              ^ formal_transition: 'Furthermore': cut it, or use 'And' / 'On top of that'
              ^ ai_slop: 'seamless': replace with plain English
              ^ vague_abstraction: 'multiple': say how many, or name them
  >> AI  (0.99) Additionally, the solution leverages robust infrastructure to deliver scalable outcomes for every stakeholder.
              ^ formal_verb: 'deliver': try 'gives you' or just describe what it does
              ^ formal_transition: 'Additionally': cut it, or use 'And' / 'Plus'
              ^ ai_slop: 'leverages': replace with plain English
              ^ ai_slop: 'robust': replace with plain English
     HUM (0.90) I do not love the price, though, and my brother thinks it is too slow.
     HUM (0.55) We went back to the old one after about a week, mostly because the export kept failing on his laptop and no...

  Structure and style (separate from the model score):
    [medium] Stock vocabulary: Furthermore, the platform provides a seamless experience for modern te
             -> Replace with the plain word, or say the specific thing it stands for.
    [medium] Stock vocabulary: …ience for modern teams, and it offers comprehensive support across mu
             -> Replace with the plain word, or say the specific thing it stands for.
    [medium] Stock vocabulary: …ple regions. Additionally, the solution leverages robust infrastructu
             -> Replace with the plain word, or say the specific thing it stands for.
    [medium] Stock vocabulary: …ons. Additionally, the solution leverages robust infrastructure to de
             -> Replace with the plain word, or say the specific thing it stands for.

[exit 0, 33 s]

PS> "{0:n0} MB" -f ((Get-ChildItem $env:HF_HOME -Recurse -File | Measure-Object Length -Sum).Sum / 1MB)
148 MB
[exit 0, 0 s]

PS> Get-ChildItem (Join-Path $env:HF_HOME hub) -Name
.locks
models--nakas--gpttrace-ettin150-text-v5e
CACHEDIR.TAG
[exit 0, 0 s]

PS> python -c "import onnxruntime as o, torch; print('onnxruntime', o.__version__, o.get_available_providers()); print('torch', torch.__version__, 'cuda available:', torch.cuda.is_available())"
onnxruntime 1.32.0 ['AzureExecutionProvider', 'CPUExecutionProvider']
torch 2.15.0+cpu cuda available: False
[exit 0, 2 s]

PS> Test-Path $env:AI_DETECT_HOME
False
[exit 0, 0 s]

PS> deactivate
[exit 0, 0 s]

== the MCP server by its full path (the Claude Desktop "command" form), venv not activated

PS> Test-Path $exe; $exe
True
C:\Users\<user>\ai-detect-proof\ai-detect\.venv\Scripts\ai-detect-mcp.exe
[exit 0, 0 s]

PS> node $Smoke $exe
initialize ok: ai-detect 2.0.0, protocol 2025-06-18, instructions 1045 chars
tools/list ok: 9 tools: compare_texts, detect_ai_file, detect_ai_text, detect_ai_url, get_model_status, list_models, open_dashboard, prefetch, scan_batch
scan ok: model gpttrace-150m, sentence score 63.4%, document 23.8%, sentences 2, dashboard http://127.0.0.1:8765/#/scan/20261125-065158-e15688
SMOKE PASS
[exit 0, 6 s]

PS> Get-ChildItem $env:AI_DETECT_HOME -Recurse -Name
history
engine.log
history\20261125-065158-e15688.json
[exit 0, 0 s]

== WINDOWS PROOF DONE
```


## Transcript 2: the JSON config form

```text
== the config file, as written

PS> Get-Content claude_desktop_config.json
{
  "mcpServers": {
    "ai-detect": {
      "command": "C:\\Users\\<user>\\ai-detect-proof\\ai-detect\\.venv\\Scripts\\ai-detect-mcp.exe"
    }
  }
}
[exit , 0 s]

== parsed as JSON, and the parsed command started by the MCP smoke test (no shell, venv not activated)

PS> node -e "const c = JSON.parse(require('fs').readFileSync('claude_desktop_config.json', 'utf8').replace(/^?/, '')); console.log(c.mcpServers['ai-detect'].command)"
C:\Users\<user>\ai-detect-proof\ai-detect\.venv\Scripts\ai-detect-mcp.exe
[exit 0, 0 s]

PS> node $Smoke $parsed
initialize ok: ai-detect 2.0.0, protocol 2025-06-18, instructions 1045 chars
tools/list ok: 9 tools: compare_texts, detect_ai_file, detect_ai_text, detect_ai_url, get_model_status, list_models, open_dashboard, prefetch, scan_batch
scan ok: model gpttrace-150m, sentence score 63.4%, document 23.8%, sentences 2, dashboard http://127.0.0.1:8765/#/scan/20261125-071417-4cad0f
SMOKE PASS
[exit 0, 6 s]

== the same file with single backslashes is not valid JSON

PS> node -e "try { JSON.parse(require('fs').readFileSync('bad_config.json', 'utf8').replace(/^?/, '')); console.log('parsed') } catch (e) { console.log('JSON error: ' + e.message) }"
JSON error: Bad escaped character in JSON at position 60 (line 4 column 22)
[exit 0, 0 s]
```

