# Proof: install and first run on Linux, 25 Nov 2026

Run on 25 Nov 2026 in Docker containers created for this and removed afterwards (the three base images were removed too). Host: Docker Desktop on Windows 11, linux/x86_64, 16 CPUs. Nothing was mounted from the host (`docker inspect` reported 0 mounts for every container). The code was a `git bundle` of the unpushed branch `rebuild-2026-11`, copied in with `docker cp` and cloned inside the container. Each command line below is followed by its real output, its exit code and its wall-clock time.

Not run: macOS, any ARM machine, any GPU.

## Results

| # | Question | Result |
|---|---|---|
| 1 | `pip install .` with the distro Python and no virtual environment | Refused: `error: externally-managed-environment` (Debian 12 with pip 23.0.1, Ubuntu 24.04 with pip 24.0). Exit 1. `python3 -m pip install .` gives the same |
| 2 | venv, then `pip install .` from the default index (debian:12) | Works. 432 s. The venv is 5.7 GB: 3.0 GB of `nvidia-*` CUDA libraries, 1.2 GB of torch (2.15.0+cu132), 78 MB of onnxruntime |
| 3 | `ai-detect --version` | `ai-detect 2.0.0` |
| 4 | A bare `ai-detect sample.txt` (no `--model`) | Downloads `gpttrace-150m` (148 MB on disk) and scores on `CPUExecutionProvider`. 22 s for the first run including the download; 1 s for the second. `--model desklib` was not needed, and nothing was written to `~/.ai-detect` |
| 5 | CPU-only PyTorch in one step: `pip install . --extra-index-url https://download.pytorch.org/whl/cpu` | Works on all three images: torch 2.15.0+cpu, no `nvidia-*` packages, venv 1.3 to 1.4 GB. 127 s (debian:12), 131 s (debian:12-slim), 69 s (ubuntu:24.04) |
| 6 | CPU-only PyTorch in two steps: `pip install torch --index-url https://download.pytorch.org/whl/cpu` first | **Fails on Debian 12** with its pip 23.0.1 (`inconsistent Name: expected 'typing-extensions', but metadata has 'typing_extensions'`, then `No matching distribution found for flit_core`). Works on Ubuntu 24.04 (pip 24.0, 63 s). On Debian 12 it worked after `pip install --upgrade pip` inside the venv (pip 26.3, 40 s; checked by hand in the first container, not in the transcript) |
| 7 | An `.html` file before the `[web]` extra | One message with the two install commands, exit 1 |
| 8 | `pip install ".[web]"` | Works: playwright 1.65.2, 20 to 23 s |
| 9 | `playwright install chromium` alone, straight after | **Fails on all three images**, and so does `playwright install --with-deps chromium`: Playwright's bundled Node cannot start (`libatomic.so.1: cannot open shared object file`). Both commands print that line and install nothing (the exit code shown in the transcript is the pipe's, not theirs) |
| 10 | After `apt-get install -y libatomic1`, `playwright install chromium` alone | Downloads Chromium (700 MB in `~/.cache/ms-playwright`, 108 to 136 s). The browser still cannot start: 20 shared libraries are missing (libglib, libnss3, libX11 and others, listed below). ai-detect prints the install message with the underlying line |
| 11 | Then `playwright install --with-deps chromium` | Works (34 to 48 s). The `.html` file is rendered and scored |
| 12 | Stock image against slim image | No difference. `debian:12`, `debian:12-slim` and `ubuntu:24.04` each needed all three steps: `libatomic1`, the browser download, and `--with-deps` |

The three containers of part B ran at the same time, while another job was using the CPU, so their times are on the slow side.

Sizes after part B (CPU-only torch, `[web]` extra, Chromium, the default model): venv 1.5 GB, `~/.cache/ms-playwright` 700 MB, `~/.cache/huggingface` 148 MB.

In the case of step 9 ai-detect was reported to print a Python traceback before 25 Nov 2026 (not re-run here). It now prints:

```text
URL input needs Playwright and its Chromium build, which are not installed.
From the ai-detect folder run:
    pip install ".[web]"
    playwright install chromium
If both are installed and the browser still cannot start, the system is missing libraries it needs. On Debian or Ubuntu run (as root, or with sudo):
    apt-get install -y libatomic1
    playwright install --with-deps chromium
(libatomic1 is for Playwright's own driver: without it neither playwright command can run, and they print 'libatomic.so.1: cannot open shared object file'.)
The underlying error was: Exception: Connection closed while reading from the driver
```

## Transcript A: `debian:12`, distro Python, default index

Commit 84bfef3.

```text
== image

$ cat /etc/os-release | head -4
PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"
NAME="Debian GNU/Linux"
VERSION_ID="12"
VERSION="12 (bookworm)"
[exit 0, 0 s]

$ uname -m
x86_64
[exit 0, 0 s]

$ apt-get update -qq && apt-get install -y -qq --no-install-recommends python3 python3-venv python3-pip git ca-certificates > /dev/null
debconf: delaying package configuration, since apt-utils is not installed
[exit 0, 45 s]

$ python3 --version; pip --version; git --version
Python 3.11.2
pip 23.0.1 from /usr/lib/python3/dist-packages/pip (python 3.11)
git version 2.39.5
[exit 0, 0 s]

== the code: a clone of the git bundle copied into the container

$ git clone -q -b rebuild-2026-11 /proof/ai-detect.bundle /root/ai-detect && cd /root/ai-detect && git log --oneline -1
84bfef3 feat: default model is gpttrace-150m; onnxruntime is a core dependency; five fixes found while documenting
[exit 0, 0 s]

== WITHOUT a virtual environment

$ pip install .
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try apt install
    python3-xyz, where xyz is the package you are trying to
    install.

    If you wish to install a non-Debian-packaged Python package,
    create a virtual environment using python3 -m venv path/to/venv.
    Then use path/to/venv/bin/python and path/to/venv/bin/pip. Make
    sure you have python3-full installed.

    If you wish to install a non-Debian packaged Python application,
    it may be easiest to use pipx install xyz, which will manage a
    virtual environment for you. Make sure you have pipx installed.

    See /usr/share/doc/python3.11/README.venv for more information.

note: If you believe this is a mistake, please contact your Python installation or OS distribution provider. You can override this, at the risk of breaking your Python installation or OS, by passing --break-system-packages.
hint: See PEP 668 for the detailed specification.
[exit 1, 0 s]

$ python3 -m pip install .
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try apt install
    python3-xyz, where xyz is the package you are trying to
    install.

    If you wish to install a non-Debian-packaged Python package,
    create a virtual environment using python3 -m venv path/to/venv.
    Then use path/to/venv/bin/python and path/to/venv/bin/pip. Make
    sure you have python3-full installed.

    If you wish to install a non-Debian packaged Python application,
    it may be easiest to use pipx install xyz, which will manage a
    virtual environment for you. Make sure you have pipx installed.

    See /usr/share/doc/python3.11/README.venv for more information.

note: If you believe this is a mistake, please contact your Python installation or OS distribution provider. You can override this, at the risk of breaking your Python installation or OS, by passing --break-system-packages.
hint: See PEP 668 for the detailed specification.
[exit 1, 1 s]

== WITH a virtual environment (default PyPI index)

$ python3 -m venv /root/venv
[exit 0, 1 s]
$ . /root/venv/bin/activate

$ pip --version
pip 23.0.1 from /root/venv/lib/python3.11/site-packages/pip (python 3.11)
[exit 0, 1 s]

$ pip install . 2>&1 | tail -n 25
  Downloading rich-15.0.0-py3-none-any.whl (310 kB)
Collecting annotated-doc>=0.0.2
  Downloading annotated_doc-0.0.7-py3-none-any.whl (5.3 kB)
Collecting cffi>=2.0.0
  Downloading cffi-2.1.1-cp311-cp311-manylinux2014_x86_64.manylinux_2_17_x86_64.whl (217 kB)
Collecting markdown-it-py>=2.2.0
  Downloading markdown_it_py-4.3.0-py3-none-any.whl (96 kB)
Collecting pygments<3.0.0,>=2.13.0
  Downloading pygments-2.21.0-py3-none-any.whl (1.3 MB)
Collecting pycparser
  Downloading pycparser-3.12-py3-none-any.whl (62 kB)
Collecting mdurl~=0.1
  Downloading mdurl-0.1.2-py3-none-any.whl (10.0 kB)
Building wheels for collected packages: ai-detect
  Building wheel for ai-detect (pyproject.toml): started
  Building wheel for ai-detect (pyproject.toml): finished with status 'done'
  Created wheel for ai-detect: filename=ai_detect-2.0.0-py3-none-any.whl size=140773 sha256=e32114be9b2143ba83737f7a26fa54a7c22946d73612fc6f2d8da1bc140aff24
  Stored in directory: /root/.cache/pip/wheels/31/7e/3c/48365454855e744c9384adbccd29a35034272befcc6aeb2dfe
Successfully built ai-detect
Installing collected packages: nvidia-cusparselt-cu13, mpmath, flatbuffers, cuda-toolkit, typing_extensions, truststore, triton, tqdm, sympy, shellingham, setuptools, safetensors, rpds-py, regex, pyyaml, python-multipart, pyjwt, pygments, pycparser, protobuf, packaging, nvidia-nvtx, nvidia-nvjitlink, nvidia-nccl-cu13, nvidia-cufile, nvidia-cuda-runtime, nvidia-cuda-nvrtc, nvidia-cuda-cupti, nvidia-cuda-cccl, numpy, networkx, mdurl, MarkupSafe, idna, hf-xet, h11, fsspec, filelock, cuda-pathfinder, click, attrs, annotated-types, annotated-doc, uvicorn, typing-inspection, referencing, pydantic-core, opentelemetry-api, onnxruntime, nvidia-nvshmem-cu13, nvidia-cusparse, nvidia-cufft, nvidia-cublas, markdown-it-py, jinja2, httpcore2, cuda-bindings, cffi, anyio, starlette, rich, pydantic, nvidia-cusolver, nvidia-cudnn-cu13, jsonschema-specifications, httpx2, cryptography, typer, sse-starlette, mcp-types, jsonschema, huggingface-hub, torch, tokenizers, mcp, transformers, ai-detect
  Attempting uninstall: setuptools
    Found existing installation: setuptools 66.1.1
    Uninstalling setuptools-66.1.1:
      Successfully uninstalled setuptools-66.1.1
Successfully installed MarkupSafe-3.0.4 ai-detect-2.0.0 annotated-doc-0.0.7 annotated-types-0.8.0 anyio-4.16.0 attrs-26.1.0 cffi-2.1.1 click-8.5.1 cryptography-50.0.2 cuda-bindings-13.5.0 cuda-pathfinder-1.9.1 cuda-toolkit-13.2.2 filelock-4.3.1 flatbuffers-25.12.19 fsspec-2026.9.0 h11-0.16.0 hf-xet-1.8.0 httpcore2-2.16.2 httpx2-2.16.2 huggingface-hub-2.4.0 idna-3.20 jinja2-3.1.6 jsonschema-4.26.0 jsonschema-specifications-2025.9.1 markdown-it-py-4.3.0 mcp-2.3.0 mcp-types-2.3.0 mdurl-0.1.2 mpmath-1.3.0 networkx-3.6.1 numpy-2.4.6 nvidia-cublas-13.4.1.3 nvidia-cuda-cccl-13.3.5.0.6 nvidia-cuda-cupti-13.2.86 nvidia-cuda-nvrtc-13.2.86 nvidia-cuda-runtime-13.2.86 nvidia-cudnn-cu13-9.26.0.51 nvidia-cufft-12.2.0.57 nvidia-cufile-1.17.1.22 nvidia-cusolver-12.2.0.11 nvidia-cusparse-12.7.10.12 nvidia-cusparselt-cu13-0.8.1 nvidia-nccl-cu13-2.30.7 nvidia-nvjitlink-13.5.37 nvidia-nvshmem-cu13-3.7.2 nvidia-nvtx-13.2.86 onnxruntime-1.32.0 opentelemetry-api-1.45.2 packaging-26.4 protobuf-7.36.2 pycparser-3.12 pydantic-2.14.4 pydantic-core-2.50.5 pygments-2.21.0 pyjwt-2.15.1 python-multipart-0.0.34 pyyaml-6.0.4 referencing-0.37.0 regex-2026.11.24 rich-15.0.0 rpds-py-2026.9.1 safetensors-0.8.0 setuptools-84.2.1 shellingham-1.5.4 sse-starlette-3.7.1 starlette-1.10.0 sympy-1.14.0 tokenizers-0.23.3 torch-2.15.0 tqdm-4.70.1 transformers-5.24.1 triton-3.9.0 truststore-0.10.5 typer-0.29.2 typing-inspection-0.4.5 typing_extensions-4.16.0 uvicorn-0.54.0
[exit 0, 432 s]

$ pip list 2>/dev/null | grep -i -E '^(ai-detect|torch|onnxruntime|transformers|tokenizers|huggingface|mcp|numpy|nvidia|triton|playwright)'
ai-detect                 2.0.0
huggingface_hub           2.4.0
mcp                       2.3.0
mcp-types                 2.3.0
numpy                     2.4.6
nvidia-cublas             13.4.1.3
nvidia-cuda-cccl          13.3.5.0.6
nvidia-cuda-cupti         13.2.86
nvidia-cuda-nvrtc         13.2.86
nvidia-cuda-runtime       13.2.86
nvidia-cudnn-cu13         9.26.0.51
nvidia-cufft              12.2.0.57
nvidia-cufile             1.17.1.22
nvidia-cusolver           12.2.0.11
nvidia-cusparse           12.7.10.12
nvidia-cusparselt-cu13    0.8.1
nvidia-nccl-cu13          2.30.7
nvidia-nvjitlink          13.5.37
nvidia-nvshmem-cu13       3.7.2
nvidia-nvtx               13.2.86
onnxruntime               1.32.0
tokenizers                0.23.3
torch                     2.15.0
transformers              5.24.1
triton                    3.9.0
[exit 0, 1 s]

$ du -sh /root/venv
5.7G	/root/venv
[exit 0, 0 s]

$ du -sh /root/venv/lib/python3*/site-packages/nvidia /root/venv/lib/python3*/site-packages/torch /root/venv/lib/python3*/site-packages/onnxruntime 2>/dev/null
3.0G	/root/venv/lib/python3.11/site-packages/nvidia
1.2G	/root/venv/lib/python3.11/site-packages/torch
78M	/root/venv/lib/python3.11/site-packages/onnxruntime
[exit 0, 0 s]

$ which ai-detect ai-detect-mcp
/root/venv/bin/ai-detect
/root/venv/bin/ai-detect-mcp
[exit 0, 0 s]

$ ai-detect --version
ai-detect 2.0.0
[exit 0, 0 s]

$ ai-detect models
model               size  licence       RAID rank   status          label
desklib          1736 MB  MIT           42 of 61    not downloaded  desklib/ai-text-detector-v1.01 (DeBERTa-v3-large)
light             126 MB  MIT           36 of 61    not downloaded  TMR ai-text-detector (RoBERTa-base, int8 ONNX)
gpttrace-150m     151 MB  CC-BY-SA-4.0  4 of 61     not downloaded  GPTTrace Ettin-150M v5e (int8 ONNX) (default)
gpttrace-1b       951 MB  CC-BY-SA-4.0  2 of 61     not downloaded  GPTTrace Ettin-1B v8s (4-bit ONNX)
tabularis         598 MB  MIT           21 of 61    not downloaded  Tabularis ModernBERT R1.1
conpara          1738 MB  MIT           20 of 61    not downloaded  DeBERTa-ConPara (DeBERTa-v3-large)

RAID rank: TPR at 5% FPR, all attacks, read 2026-11-24 (https://raid-bench.xyz/leaderboard). Whole documents, not single sentences.
[exit 0, 0 s]

== first scan: a bare 'ai-detect sample.txt' (no --model), which downloads the default

$ ai-detect /root/sample.txt
Downloading GPTTrace Ettin-150M v5e (int8 ONNX) (~151 MB, one time; resumes if interrupted)...
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.

  gpttrace-150m  [............................]   0.0% of 148 MB   
  gpttrace-150m  [............................]   0.0% of 148 MB about 139 min left   
  ... (59 more progress lines, not shown)
  gpttrace-150m  [#...........................]   6.8% of 148 MB less than a minute left   
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

[exit 0, 22 s]

$ du -sh /root/.cache/huggingface
148M	/root/.cache/huggingface
[exit 0, 0 s]

$ ls /root/.cache/huggingface/hub
CACHEDIR.TAG
blobs
models--nakas--gpttrace-ettin150-text-v5e
[exit 0, 0 s]

== second scan: model already on disk

$ ai-detect /root/sample.txt | head -n 8
Loading GPTTrace Ettin-150M v5e (int8 ONNX) (ONNX)...
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
Model loaded via onnxruntime CPUExecutionProvider (GPTTrace Ettin-150M v5e (int8 ONNX))

  Model AI score (raw mean of sentences): 63.4% - LIKELY AI   [gpttrace-150m]
  Assessment: Uncertain (calibrated document score 54.1%, confidence low)
  Sentences: 2 AI / 2 Human / 4 scored
  SDSL: mean=18.0 words, stddev=4.9, CV=0.27 (very uniform (AI-like))
  Patterns: 3 formal verb, 3 ai slop, 2 formal transition, 1 vague abstraction
  Document score (raw): 82.9% over 1 passage(s), 72 words, confidence low
  At the 5%-false-positive operating point: 2 of 4 sentences flagged, document 54.1%
[exit 0, 1 s]

$ ai-detect models
model               size  licence       RAID rank   status          label
desklib          1736 MB  MIT           42 of 61    not downloaded  desklib/ai-text-detector-v1.01 (DeBERTa-v3-large)
light             126 MB  MIT           36 of 61    not downloaded  TMR ai-text-detector (RoBERTa-base, int8 ONNX)
gpttrace-150m     151 MB  CC-BY-SA-4.0  4 of 61     downloaded      GPTTrace Ettin-150M v5e (int8 ONNX) (default)
gpttrace-1b       951 MB  CC-BY-SA-4.0  2 of 61     not downloaded  GPTTrace Ettin-1B v8s (4-bit ONNX)
tabularis         598 MB  MIT           21 of 61    not downloaded  Tabularis ModernBERT R1.1
conpara          1738 MB  MIT           20 of 61    not downloaded  DeBERTa-ConPara (DeBERTa-v3-large)

RAID rank: TPR at 5% FPR, all attacks, read 2026-11-24 (https://raid-bench.xyz/leaderboard). Whole documents, not single sentences.
[exit 0, 1 s]

$ python -c "import onnxruntime as o, torch; print('onnxruntime', o.__version__, o.get_available_providers()); print('torch', torch.__version__, 'cuda available:', torch.cuda.is_available())"
onnxruntime 1.32.0 ['AzureExecutionProvider', 'CPUExecutionProvider']
torch 2.15.0+cu132 cuda available: False
[exit 0, 1 s]

$ ls /root/.ai-detect 2>&1
ls: cannot access '/root/.ai-detect': No such file or directory
[exit 2, 0 s]

== PART A DONE
```


## Transcript B1: `debian:12` (stock), CPU-only PyTorch, `[web]`, Playwright

Commit b7d3d93. The scan output is cut to its first lines; the full first-scan output is in transcript A.

```text
== image (stock)

$ cat /etc/os-release | head -4
PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"
NAME="Debian GNU/Linux"
VERSION_ID="12"
VERSION="12 (bookworm)"
[exit 0, 0 s]

$ apt-get update -qq && apt-get install -y -qq --no-install-recommends python3 python3-venv python3-pip git ca-certificates > /dev/null
debconf: delaying package configuration, since apt-utils is not installed
[exit 0, 27 s]

$ python3 --version; pip --version
Python 3.11.2
pip 23.0.1 from /usr/lib/python3/dist-packages/pip (python 3.11)
[exit 0, 1 s]

$ git clone -q -b rebuild-2026-11 /proof/ai-detect.bundle /root/ai-detect && cd /root/ai-detect && git log --oneline -1
b7d3d93 fix: read an article whose own class name holds a noise word; clearer message when Playwright's driver cannot start
[exit 0, 0 s]

== WITHOUT a virtual environment

$ pip install . 2>&1 | head -n 4
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try apt install
[exit 0, 0 s]

== CPU-only PyTorch, the usual two-step form, with the distro's pip

$ python3 -m venv /root/venv-a
[exit 0, 2 s]
$ . /root/venv-a/bin/activate

$ pip --version
pip 23.0.1 from /root/venv-a/lib/python3.11/site-packages/pip (python 3.11)
[exit 0, 0 s]

$ pip install torch --index-url https://download.pytorch.org/whl/cpu 2>&1 | grep -E 'inconsistent Name|flit_core|^ERROR|^error|Successfully installed' | cut -c1-400
Discarding https://files.pythonhosted.org/packages/49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80/typing_extensions-4.16.0-py3-none-any.whl#sha256=481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8 (from https://download.pytorch.org/whl/cpu/typing-extensions/) (requires-python:>=3.9): Requested typing-extensions>=4.13.0 from https://files.pythonhosted.org/packages
      ERROR: Could not find a version that satisfies the requirement flit_core<4,>=3.11 (from versions: none)
      ERROR: No matching distribution found for flit_core<4,>=3.11
error: subprocess-exited-with-error
[exit 0, 1 s]

$ pip list 2>/dev/null | grep -i -E '^torch '
[exit 1, 1 s]

== CPU-only PyTorch in one step: pip install . with the CPU index as an extra index

$ python3 -m venv /root/venv
[exit 0, 2 s]
$ . /root/venv/bin/activate

$ pip install . --extra-index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -n 1 | cut -c1-700
Successfully installed MarkupSafe-3.0.4 ai-detect-2.0.0 annotated-doc-0.0.7 annotated-types-0.8.0 anyio-4.16.0 attrs-26.1.0 cffi-2.1.1 click-8.5.1 cryptography-50.0.2 filelock-4.3.1 flatbuffers-25.12.19 fsspec-2026.9.0 h11-0.16.0 hf-xet-1.8.0 httpcore2-2.16.2 httpx2-2.16.2 huggingface-hub-2.4.0 idna-3.20 jinja2-3.1.6 jsonschema-4.26.0 jsonschema-specifications-2025.9.1 markdown-it-py-4.3.0 mcp-2.3.0 mcp-types-2.3.0 mdurl-0.1.2 mpmath-1.3.0 networkx-3.6.1 numpy-2.4.6 onnxruntime-1.32.0 opentelemetry-api-1.45.2 packaging-26.4 protobuf-7.36.2 pycparser-3.12 pydantic-2.14.4 pydantic-core-2.50.5 pygments-2.21.0 pyjwt-2.15.1 python-multipart-0.0.34 pyyaml-6.0.4 referencing-0.37.0 regex-2026.11.24
[exit 0, 127 s]

$ pip list 2>/dev/null | grep -i -E '^(ai-detect|torch|onnxruntime|transformers|mcp|nvidia|playwright) '
ai-detect                 2.0.0
mcp                       2.3.0
onnxruntime               1.32.0
torch                     2.15.0+cpu
transformers              5.24.1
[exit 0, 1 s]

$ du -sh /root/venv
1.4G	/root/venv
[exit 0, 0 s]

$ ai-detect --version
ai-detect 2.0.0
[exit 0, 0 s]

$ ai-detect /root/sample.txt 2>&1 | tr '\r' '\n' | grep -v -E '^\s*gpttrace-150m +\[' | head -n 14
Downloading GPTTrace Ettin-150M v5e (int8 ONNX) (~151 MB, one time; resumes if interrupted)...
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.

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
[exit 0, 61 s]

$ du -sh /root/.cache/huggingface
148M	/root/.cache/huggingface
[exit 0, 0 s]

== an .html file before the [web] extra

$ ai-detect --file /root/page.html
URL input needs Playwright and its Chromium build, which are not installed.
From the ai-detect folder run:
    pip install ".[web]"
    playwright install chromium
[exit 1, 0 s]

== the [web] extra

$ pip install '.[web]' 2>&1 | tail -n 1
Successfully installed ai-detect-2.0.0 greenlet-3.5.6 playwright-1.65.2
[exit 0, 23 s]

$ pip list 2>/dev/null | grep -i -E '^(playwright|greenlet) '
greenlet                  3.5.6
playwright                1.65.2
[exit 0, 1 s]

== Playwright installed, no browser downloaded yet

$ ai-detect --file /root/page.html
/root/venv/lib/python3.11/site-packages/playwright/driver/node: error while loading shared libraries: libatomic.so.1: cannot open shared object file: No such file or directory
URL input needs Playwright and its Chromium build, which are not installed.
From the ai-detect folder run:
    pip install ".[web]"
    playwright install chromium
If both are installed and the browser still cannot start, the system is missing libraries it needs. On Debian or Ubuntu run (as root, or with sudo):
    apt-get install -y libatomic1
    playwright install --with-deps chromium
(libatomic1 is for Playwright's own driver: without it neither playwright command can run, and they print 'libatomic.so.1: cannot open shared object file'.)
The underlying error was: Exception: Connection closed while reading from the driver
[exit 1, 0 s]

== playwright install chromium (alone, no --with-deps)

$ playwright install chromium 2>&1 | tr '\r' '\n' | grep -v -E '^\|| [0-9]+% of' | tail -n 12
/root/venv/lib/python3.11/site-packages/playwright/driver/node: error while loading shared libraries: libatomic.so.1: cannot open shared object file: No such file or directory
[exit 0, 0 s]

$ ldd /root/venv/lib/python3*/site-packages/playwright/driver/node | grep 'not found'
	libatomic.so.1 => not found
[exit 0, 0 s]

$ ai-detect --file /root/page.html 2>&1 | head -n 12
/root/venv/lib/python3.11/site-packages/playwright/driver/node: error while loading shared libraries: libatomic.so.1: cannot open shared object file: No such file or directory
URL input needs Playwright and its Chromium build, which are not installed.
From the ai-detect folder run:
    pip install ".[web]"
    playwright install chromium
If both are installed and the browser still cannot start, the system is missing libraries it needs. On Debian or Ubuntu run (as root, or with sudo):
    apt-get install -y libatomic1
    playwright install --with-deps chromium
(libatomic1 is for Playwright's own driver: without it neither playwright command can run, and they print 'libatomic.so.1: cannot open shared object file'.)
The underlying error was: Exception: Connection closed while reading from the driver
[exit 0, 0 s]

== playwright install --with-deps chromium, as it stands

$ playwright install --with-deps chromium 2>&1 | tr '\r' '\n' | grep -v -E '^\|| [0-9]+% of|^(Get|Hit|Ign|Fetched|Selecting|Preparing|Unpacking|Setting up|Processing|\(Reading|Reading|Building)' | tail -n 12
/root/venv/lib/python3.11/site-packages/playwright/driver/node: error while loading shared libraries: libatomic.so.1: cannot open shared object file: No such file or directory
[exit 0, 0 s]

== the library Playwright's driver needs

$ apt-get install -y -qq --no-install-recommends libatomic1 > /dev/null; dpkg -s libatomic1 | grep -E '^(Package|Status|Version)'
debconf: delaying package configuration, since apt-utils is not installed
Package: libatomic1
Status: install ok installed
Version: 12.2.0-14+deb12u1
[exit 0, 1 s]

== playwright install chromium (alone), again

$ playwright install chromium 2>&1 | tr '\r' '\n' | grep -v -E '^\|| [0-9]+% of' | tail -n 12
Downloading Chrome for Testing 159.0.8154.6 (playwright chromium v1255) from https://cdn.playwright.dev/builds/cft/159.0.8154.6/linux64/chrome-linux64.zip
Chrome for Testing 159.0.8154.6 (playwright chromium v1255) downloaded to /root/.cache/ms-playwright/chromium-1255
Downloading FFmpeg (playwright ffmpeg v1013) from https://cdn.playwright.dev/dbazure/download/playwright/builds/ffmpeg/1013/ffmpeg-linux.zip
FFmpeg (playwright ffmpeg v1013) downloaded to /root/.cache/ms-playwright/ffmpeg-1013
Downloading Chrome Headless Shell 159.0.8154.6 (playwright chromium-headless-shell v1255) from https://cdn.playwright.dev/builds/cft/159.0.8154.6/linux64/chrome-headless-shell-linux64.zip
Chrome Headless Shell 159.0.8154.6 (playwright chromium-headless-shell v1255) downloaded to /root/.cache/ms-playwright/chromium_headless_shell-1255
[exit 0, 108 s]

$ du -sh /root/.cache/ms-playwright; ls /root/.cache/ms-playwright
700M	/root/.cache/ms-playwright
chromium-1255
chromium_headless_shell-1255
ffmpeg-1013
[exit 0, 0 s]

== does the browser start with 'playwright install chromium' alone?

$ for f in /root/.cache/ms-playwright/chromium_headless_shell-*/chrome-*/*headless*shell; do echo $f; ldd $f | grep 'not found' | sort -u; done
/root/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/LICENSE.headless_shell
	not a dynamic executable
/root/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell
	libX11.so.6 => not found
	libXcomposite.so.1 => not found
	libXdamage.so.1 => not found
	libXext.so.6 => not found
	libXfixes.so.3 => not found
	libXrandr.so.2 => not found
	libasound.so.2 => not found
	libatk-1.0.so.0 => not found
	libatk-bridge-2.0.so.0 => not found
	libatspi.so.0 => not found
	libdbus-1.so.3 => not found
	libgbm.so.1 => not found
	libgio-2.0.so.0 => not found
	libglib-2.0.so.0 => not found
	libgobject-2.0.so.0 => not found
	libnspr4.so => not found
	libnss3.so => not found
	libnssutil3.so => not found
	libxcb.so.1 => not found
	libxkbcommon.so.0 => not found
[exit 0, 0 s]

$ ai-detect --file /root/page.html 2>&1 | head -n 14
URL input needs Playwright and its Chromium build, which are not installed.
From the ai-detect folder run:
    pip install ".[web]"
    playwright install chromium
If both are installed and the browser still cannot start, the system is missing libraries it needs. On Debian or Ubuntu run (as root, or with sudo):
    apt-get install -y libatomic1
    playwright install --with-deps chromium
(libatomic1 is for Playwright's own driver: without it neither playwright command can run, and they print 'libatomic.so.1: cannot open shared object file'.)
The underlying error was: TargetClosedError: [pid=3750][err] /root/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell: error while loading shared libraries: libglib-2.0.so.0: cannot open shared object file: No such file or directory
[exit 0, 1 s]

== playwright install --with-deps chromium

$ playwright install --with-deps chromium 2>&1 | tr '\r' '\n' | grep -v -E '^\|| [0-9]+% of|^(Get|Hit|Ign|Fetched|Selecting|Preparing|Unpacking|Setting up|Processing|\(Reading|Reading|Building)' | tail -n 14

[exit 0, 36 s]

$ for f in /root/.cache/ms-playwright/chromium_headless_shell-*/chrome-*/*headless*shell; do ldd $f | grep -c 'not found'; done
	not a dynamic executable
0
0
[exit 1, 0 s]

$ ai-detect --file /root/page.html 2>&1 | head -n 14
Loading GPTTrace Ettin-150M v5e (int8 ONNX) (ONNX)...
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
Model loaded via onnxruntime CPUExecutionProvider (GPTTrace Ettin-150M v5e (int8 ONNX))

  Model AI score (raw mean of sentences): 63.4% - LIKELY AI   [gpttrace-150m]
  Assessment: Uncertain (calibrated document score 54.1%, confidence low)
  Sentences: 2 AI / 2 Human / 4 scored (1 skipped <5 words)
  SDSL: mean=18.0 words, stddev=4.9, CV=0.27 (very uniform (AI-like))
  Patterns: 3 formal verb, 3 ai slop, 2 formal transition, 1 vague abstraction
  Document score (raw): 82.9% over 1 passage(s), 72 words, confidence low
  At the 5%-false-positive operating point: 2 of 4 sentences flagged, document 54.1%
  Note: Only 72 words. The model cards call results under about 150 words unreliable.
  Note: Sentence scores are split, which can mean mixed authorship or an edited draft. Single-sentence scores are a rough signal.

[exit 0, 2 s]

$ du -sh /root/venv /root/.cache/ms-playwright /root/.cache/huggingface
1.5G	/root/venv
700M	/root/.cache/ms-playwright
148M	/root/.cache/huggingface
[exit 0, 0 s]

== PART B DONE (stock)
```


## Transcript B2: `debian:12-slim`

```text
== image (slim)

$ cat /etc/os-release | head -4
PRETTY_NAME="Debian GNU/Linux 12 (bookworm)"
NAME="Debian GNU/Linux"
VERSION_ID="12"
VERSION="12 (bookworm)"
[exit 0, 0 s]

$ apt-get update -qq && apt-get install -y -qq --no-install-recommends python3 python3-venv python3-pip git ca-certificates > /dev/null
debconf: delaying package configuration, since apt-utils is not installed
[exit 0, 23 s]

$ python3 --version; pip --version
Python 3.11.2
pip 23.0.1 from /usr/lib/python3/dist-packages/pip (python 3.11)
[exit 0, 0 s]

$ git clone -q -b rebuild-2026-11 /proof/ai-detect.bundle /root/ai-detect && cd /root/ai-detect && git log --oneline -1
b7d3d93 fix: read an article whose own class name holds a noise word; clearer message when Playwright's driver cannot start
[exit 0, 0 s]

== WITHOUT a virtual environment

$ pip install . 2>&1 | head -n 4
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try apt install
[exit 0, 0 s]

== CPU-only PyTorch, the usual two-step form, with the distro's pip

$ python3 -m venv /root/venv-a
[exit 0, 2 s]
$ . /root/venv-a/bin/activate

$ pip --version
pip 23.0.1 from /root/venv-a/lib/python3.11/site-packages/pip (python 3.11)
[exit 0, 0 s]

$ pip install torch --index-url https://download.pytorch.org/whl/cpu 2>&1 | grep -E 'inconsistent Name|flit_core|^ERROR|^error|Successfully installed' | cut -c1-400
Discarding https://files.pythonhosted.org/packages/49/d3/b8441a820a491ddfc024b0b0cf0393375b75ea13866d9c66727e54c2fc80/typing_extensions-4.16.0-py3-none-any.whl#sha256=481caa481374e813c1b176ada14e97f1f67a4539ce9cfeb3f350d78d6370c2e8 (from https://download.pytorch.org/whl/cpu/typing-extensions/) (requires-python:>=3.9): Requested typing-extensions>=4.13.0 from https://files.pythonhosted.org/packages
      ERROR: Could not find a version that satisfies the requirement flit_core<4,>=3.11 (from versions: none)
      ERROR: No matching distribution found for flit_core<4,>=3.11
error: subprocess-exited-with-error
[exit 0, 2 s]

$ pip list 2>/dev/null | grep -i -E '^torch '
[exit 1, 0 s]

== CPU-only PyTorch in one step: pip install . with the CPU index as an extra index

$ python3 -m venv /root/venv
[exit 0, 2 s]
$ . /root/venv/bin/activate

$ pip install . --extra-index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -n 1 | cut -c1-700
Successfully installed MarkupSafe-3.0.4 ai-detect-2.0.0 annotated-doc-0.0.7 annotated-types-0.8.0 anyio-4.16.0 attrs-26.1.0 cffi-2.1.1 click-8.5.1 cryptography-50.0.2 filelock-4.3.1 flatbuffers-25.12.19 fsspec-2026.9.0 h11-0.16.0 hf-xet-1.8.0 httpcore2-2.16.2 httpx2-2.16.2 huggingface-hub-2.4.0 idna-3.20 jinja2-3.1.6 jsonschema-4.26.0 jsonschema-specifications-2025.9.1 markdown-it-py-4.3.0 mcp-2.3.0 mcp-types-2.3.0 mdurl-0.1.2 mpmath-1.3.0 networkx-3.6.1 numpy-2.4.6 onnxruntime-1.32.0 opentelemetry-api-1.45.2 packaging-26.4 protobuf-7.36.2 pycparser-3.12 pydantic-2.14.4 pydantic-core-2.50.5 pygments-2.21.0 pyjwt-2.15.1 python-multipart-0.0.34 pyyaml-6.0.4 referencing-0.37.0 regex-2026.11.24
[exit 0, 131 s]

$ pip list 2>/dev/null | grep -i -E '^(ai-detect|torch|onnxruntime|transformers|mcp|nvidia|playwright) '
ai-detect                 2.0.0
mcp                       2.3.0
onnxruntime               1.32.0
torch                     2.15.0+cpu
transformers              5.24.1
[exit 0, 0 s]

$ du -sh /root/venv
1.4G	/root/venv
[exit 0, 0 s]

$ ai-detect --version
ai-detect 2.0.0
[exit 0, 0 s]

$ ai-detect /root/sample.txt 2>&1 | tr '\r' '\n' | grep -v -E '^\s*gpttrace-150m +\[' | head -n 14
Downloading GPTTrace Ettin-150M v5e (int8 ONNX) (~151 MB, one time; resumes if interrupted)...
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.

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
[exit 0, 60 s]

$ du -sh /root/.cache/huggingface
148M	/root/.cache/huggingface
[exit 0, 0 s]

== an .html file before the [web] extra

$ ai-detect --file /root/page.html
URL input needs Playwright and its Chromium build, which are not installed.
From the ai-detect folder run:
    pip install ".[web]"
    playwright install chromium
[exit 1, 1 s]

== the [web] extra

$ pip install '.[web]' 2>&1 | tail -n 1
Successfully installed ai-detect-2.0.0 greenlet-3.5.6 playwright-1.65.2
[exit 0, 22 s]

$ pip list 2>/dev/null | grep -i -E '^(playwright|greenlet) '
greenlet                  3.5.6
playwright                1.65.2
[exit 0, 1 s]

== Playwright installed, no browser downloaded yet

$ ai-detect --file /root/page.html
/root/venv/lib/python3.11/site-packages/playwright/driver/node: error while loading shared libraries: libatomic.so.1: cannot open shared object file: No such file or directory
URL input needs Playwright and its Chromium build, which are not installed.
From the ai-detect folder run:
    pip install ".[web]"
    playwright install chromium
If both are installed and the browser still cannot start, the system is missing libraries it needs. On Debian or Ubuntu run (as root, or with sudo):
    apt-get install -y libatomic1
    playwright install --with-deps chromium
(libatomic1 is for Playwright's own driver: without it neither playwright command can run, and they print 'libatomic.so.1: cannot open shared object file'.)
The underlying error was: Exception: Connection closed while reading from the driver
[exit 1, 0 s]

== playwright install chromium (alone, no --with-deps)

$ playwright install chromium 2>&1 | tr '\r' '\n' | grep -v -E '^\|| [0-9]+% of' | tail -n 12
/root/venv/lib/python3.11/site-packages/playwright/driver/node: error while loading shared libraries: libatomic.so.1: cannot open shared object file: No such file or directory
[exit 0, 0 s]

$ ldd /root/venv/lib/python3*/site-packages/playwright/driver/node | grep 'not found'
	libatomic.so.1 => not found
[exit 0, 0 s]

$ ai-detect --file /root/page.html 2>&1 | head -n 12
/root/venv/lib/python3.11/site-packages/playwright/driver/node: error while loading shared libraries: libatomic.so.1: cannot open shared object file: No such file or directory
URL input needs Playwright and its Chromium build, which are not installed.
From the ai-detect folder run:
    pip install ".[web]"
    playwright install chromium
If both are installed and the browser still cannot start, the system is missing libraries it needs. On Debian or Ubuntu run (as root, or with sudo):
    apt-get install -y libatomic1
    playwright install --with-deps chromium
(libatomic1 is for Playwright's own driver: without it neither playwright command can run, and they print 'libatomic.so.1: cannot open shared object file'.)
The underlying error was: Exception: Connection closed while reading from the driver
[exit 0, 0 s]

== playwright install --with-deps chromium, as it stands

$ playwright install --with-deps chromium 2>&1 | tr '\r' '\n' | grep -v -E '^\|| [0-9]+% of|^(Get|Hit|Ign|Fetched|Selecting|Preparing|Unpacking|Setting up|Processing|\(Reading|Reading|Building)' | tail -n 12
/root/venv/lib/python3.11/site-packages/playwright/driver/node: error while loading shared libraries: libatomic.so.1: cannot open shared object file: No such file or directory
[exit 0, 0 s]

== the library Playwright's driver needs

$ apt-get install -y -qq --no-install-recommends libatomic1 > /dev/null; dpkg -s libatomic1 | grep -E '^(Package|Status|Version)'
debconf: delaying package configuration, since apt-utils is not installed
Package: libatomic1
Status: install ok installed
Version: 12.2.0-14+deb12u1
[exit 0, 1 s]

== playwright install chromium (alone), again

$ playwright install chromium 2>&1 | tr '\r' '\n' | grep -v -E '^\|| [0-9]+% of' | tail -n 12
Downloading Chrome for Testing 159.0.8154.6 (playwright chromium v1255) from https://cdn.playwright.dev/builds/cft/159.0.8154.6/linux64/chrome-linux64.zip
Chrome for Testing 159.0.8154.6 (playwright chromium v1255) downloaded to /root/.cache/ms-playwright/chromium-1255
Downloading FFmpeg (playwright ffmpeg v1013) from https://cdn.playwright.dev/dbazure/download/playwright/builds/ffmpeg/1013/ffmpeg-linux.zip
FFmpeg (playwright ffmpeg v1013) downloaded to /root/.cache/ms-playwright/ffmpeg-1013
Downloading Chrome Headless Shell 159.0.8154.6 (playwright chromium-headless-shell v1255) from https://cdn.playwright.dev/builds/cft/159.0.8154.6/linux64/chrome-headless-shell-linux64.zip
Chrome Headless Shell 159.0.8154.6 (playwright chromium-headless-shell v1255) downloaded to /root/.cache/ms-playwright/chromium_headless_shell-1255
[exit 0, 136 s]

$ du -sh /root/.cache/ms-playwright; ls /root/.cache/ms-playwright
700M	/root/.cache/ms-playwright
chromium-1255
chromium_headless_shell-1255
ffmpeg-1013
[exit 0, 0 s]

== does the browser start with 'playwright install chromium' alone?

$ for f in /root/.cache/ms-playwright/chromium_headless_shell-*/chrome-*/*headless*shell; do echo $f; ldd $f | grep 'not found' | sort -u; done
/root/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/LICENSE.headless_shell
	not a dynamic executable
/root/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell
	libX11.so.6 => not found
	libXcomposite.so.1 => not found
	libXdamage.so.1 => not found
	libXext.so.6 => not found
	libXfixes.so.3 => not found
	libXrandr.so.2 => not found
	libasound.so.2 => not found
	libatk-1.0.so.0 => not found
	libatk-bridge-2.0.so.0 => not found
	libatspi.so.0 => not found
	libdbus-1.so.3 => not found
	libgbm.so.1 => not found
	libgio-2.0.so.0 => not found
	libglib-2.0.so.0 => not found
	libgobject-2.0.so.0 => not found
	libnspr4.so => not found
	libnss3.so => not found
	libnssutil3.so => not found
	libxcb.so.1 => not found
	libxkbcommon.so.0 => not found
[exit 0, 0 s]

$ ai-detect --file /root/page.html 2>&1 | head -n 14
URL input needs Playwright and its Chromium build, which are not installed.
From the ai-detect folder run:
    pip install ".[web]"
    playwright install chromium
If both are installed and the browser still cannot start, the system is missing libraries it needs. On Debian or Ubuntu run (as root, or with sudo):
    apt-get install -y libatomic1
    playwright install --with-deps chromium
(libatomic1 is for Playwright's own driver: without it neither playwright command can run, and they print 'libatomic.so.1: cannot open shared object file'.)
The underlying error was: TargetClosedError: [pid=3750][err] /root/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell: error while loading shared libraries: libglib-2.0.so.0: cannot open shared object file: No such file or directory
[exit 0, 0 s]

== playwright install --with-deps chromium

$ playwright install --with-deps chromium 2>&1 | tr '\r' '\n' | grep -v -E '^\|| [0-9]+% of|^(Get|Hit|Ign|Fetched|Selecting|Preparing|Unpacking|Setting up|Processing|\(Reading|Reading|Building)' | tail -n 14

[exit 0, 34 s]

$ for f in /root/.cache/ms-playwright/chromium_headless_shell-*/chrome-*/*headless*shell; do ldd $f | grep -c 'not found'; done
	not a dynamic executable
0
0
[exit 1, 0 s]

$ ai-detect --file /root/page.html 2>&1 | head -n 14
Loading GPTTrace Ettin-150M v5e (int8 ONNX) (ONNX)...
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
Model loaded via onnxruntime CPUExecutionProvider (GPTTrace Ettin-150M v5e (int8 ONNX))

  Model AI score (raw mean of sentences): 63.4% - LIKELY AI   [gpttrace-150m]
  Assessment: Uncertain (calibrated document score 54.1%, confidence low)
  Sentences: 2 AI / 2 Human / 4 scored (1 skipped <5 words)
  SDSL: mean=18.0 words, stddev=4.9, CV=0.27 (very uniform (AI-like))
  Patterns: 3 formal verb, 3 ai slop, 2 formal transition, 1 vague abstraction
  Document score (raw): 82.9% over 1 passage(s), 72 words, confidence low
  At the 5%-false-positive operating point: 2 of 4 sentences flagged, document 54.1%
  Note: Only 72 words. The model cards call results under about 150 words unreliable.
  Note: Sentence scores are split, which can mean mixed authorship or an edited draft. Single-sentence scores are a rough signal.

[exit 0, 2 s]

$ du -sh /root/venv /root/.cache/ms-playwright /root/.cache/huggingface
1.5G	/root/venv
700M	/root/.cache/ms-playwright
148M	/root/.cache/huggingface
[exit 0, 0 s]

== PART B DONE (slim)
```


## Transcript B3: `ubuntu:24.04`

```text
== image (ubuntu)

$ cat /etc/os-release | head -4
PRETTY_NAME="Ubuntu 24.04.5 LTS"
NAME="Ubuntu"
VERSION_ID="24.04"
VERSION="24.04.5 LTS (Noble Numbat)"
[exit 0, 0 s]

$ apt-get update -qq && apt-get install -y -qq --no-install-recommends python3 python3-venv python3-pip git ca-certificates > /dev/null
debconf: delaying package configuration, since apt-utils is not installed
[exit 0, 27 s]

$ python3 --version; pip --version
Python 3.12.3
pip 24.0 from /usr/lib/python3/dist-packages/pip (python 3.12)
[exit 0, 0 s]

$ git clone -q -b rebuild-2026-11 /proof/ai-detect.bundle /root/ai-detect && cd /root/ai-detect && git log --oneline -1
b7d3d93 fix: read an article whose own class name holds a noise word; clearer message when Playwright's driver cannot start
[exit 0, 0 s]

== WITHOUT a virtual environment

$ pip install . 2>&1 | head -n 4
error: externally-managed-environment

× This environment is externally managed
╰─> To install Python packages system-wide, try apt install
[exit 0, 0 s]

== CPU-only PyTorch, the usual two-step form, with the distro's pip

$ python3 -m venv /root/venv-a
[exit 0, 2 s]
$ . /root/venv-a/bin/activate

$ pip --version
pip 24.0 from /root/venv-a/lib/python3.12/site-packages/pip (python 3.12)
[exit 0, 0 s]

$ pip install torch --index-url https://download.pytorch.org/whl/cpu 2>&1 | grep -E 'inconsistent Name|flit_core|^ERROR|^error|Successfully installed' | cut -c1-400
Successfully installed MarkupSafe-3.0.3 filelock-4.2.4 fsspec-2026.9.0 jinja2-3.1.6 mpmath-1.3.0 networkx-3.7 setuptools-78.1.0 sympy-1.14.0 torch-2.15.0+cpu typing-extensions-4.16.0
[exit 0, 63 s]

$ pip list 2>/dev/null | grep -i -E '^torch '
torch             2.15.0+cpu
[exit 0, 0 s]

== CPU-only PyTorch in one step: pip install . with the CPU index as an extra index

$ python3 -m venv /root/venv
[exit 0, 2 s]
$ . /root/venv/bin/activate

$ pip install . --extra-index-url https://download.pytorch.org/whl/cpu 2>&1 | tail -n 1 | cut -c1-700
Successfully installed MarkupSafe-3.0.4 ai-detect-2.0.0 annotated-doc-0.0.7 annotated-types-0.8.0 anyio-4.16.0 attrs-26.1.0 cffi-2.1.1 click-8.5.1 cryptography-50.0.2 filelock-4.3.1 flatbuffers-25.12.19 fsspec-2026.9.0 h11-0.16.0 hf-xet-1.8.0 httpcore2-2.16.2 httpx2-2.16.2 huggingface-hub-2.4.0 idna-3.20 jinja2-3.1.6 jsonschema-4.26.0 jsonschema-specifications-2025.9.1 markdown-it-py-4.3.0 mcp-2.3.0 mcp-types-2.3.0 mdurl-0.1.2 mpmath-1.3.0 networkx-3.7 numpy-2.5.5 onnxruntime-1.32.0 opentelemetry-api-1.45.2 packaging-26.4 protobuf-7.36.2 pycparser-3.12 pydantic-2.14.4 pydantic-core-2.50.5 pygments-2.21.0 pyjwt-2.15.1 python-multipart-0.0.34 pyyaml-6.0.4 referencing-0.37.0 regex-2026.11.24 ri
[exit 0, 69 s]

$ pip list 2>/dev/null | grep -i -E '^(ai-detect|torch|onnxruntime|transformers|mcp|nvidia|playwright) '
ai-detect                 2.0.0
mcp                       2.3.0
onnxruntime               1.32.0
torch                     2.15.0+cpu
transformers              5.24.1
[exit 0, 0 s]

$ du -sh /root/venv
1.3G	/root/venv
[exit 0, 0 s]

$ ai-detect --version
ai-detect 2.0.0
[exit 0, 0 s]

$ ai-detect /root/sample.txt 2>&1 | tr '\r' '\n' | grep -v -E '^\s*gpttrace-150m +\[' | head -n 14
Downloading GPTTrace Ettin-150M v5e (int8 ONNX) (~151 MB, one time; resumes if interrupted)...
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.

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
[exit 0, 55 s]

$ du -sh /root/.cache/huggingface
148M	/root/.cache/huggingface
[exit 0, 0 s]

== an .html file before the [web] extra

$ ai-detect --file /root/page.html
URL input needs Playwright and its Chromium build, which are not installed.
From the ai-detect folder run:
    pip install ".[web]"
    playwright install chromium
[exit 1, 0 s]

== the [web] extra

$ pip install '.[web]' 2>&1 | tail -n 1
Successfully installed ai-detect-2.0.0 greenlet-3.5.6 playwright-1.65.2
[exit 0, 20 s]

$ pip list 2>/dev/null | grep -i -E '^(playwright|greenlet) '
greenlet                  3.5.6
playwright                1.65.2
[exit 0, 0 s]

== Playwright installed, no browser downloaded yet

$ ai-detect --file /root/page.html
/root/venv/lib/python3.12/site-packages/playwright/driver/node: error while loading shared libraries: libatomic.so.1: cannot open shared object file: No such file or directory
URL input needs Playwright and its Chromium build, which are not installed.
From the ai-detect folder run:
    pip install ".[web]"
    playwright install chromium
If both are installed and the browser still cannot start, the system is missing libraries it needs. On Debian or Ubuntu run (as root, or with sudo):
    apt-get install -y libatomic1
    playwright install --with-deps chromium
(libatomic1 is for Playwright's own driver: without it neither playwright command can run, and they print 'libatomic.so.1: cannot open shared object file'.)
The underlying error was: Exception: Connection closed while reading from the driver
[exit 1, 0 s]

== playwright install chromium (alone, no --with-deps)

$ playwright install chromium 2>&1 | tr '\r' '\n' | grep -v -E '^\|| [0-9]+% of' | tail -n 12
/root/venv/lib/python3.12/site-packages/playwright/driver/node: error while loading shared libraries: libatomic.so.1: cannot open shared object file: No such file or directory
[exit 0, 0 s]

$ ldd /root/venv/lib/python3*/site-packages/playwright/driver/node | grep 'not found'
	libatomic.so.1 => not found
[exit 0, 0 s]

$ ai-detect --file /root/page.html 2>&1 | head -n 12
/root/venv/lib/python3.12/site-packages/playwright/driver/node: error while loading shared libraries: libatomic.so.1: cannot open shared object file: No such file or directory
URL input needs Playwright and its Chromium build, which are not installed.
From the ai-detect folder run:
    pip install ".[web]"
    playwright install chromium
If both are installed and the browser still cannot start, the system is missing libraries it needs. On Debian or Ubuntu run (as root, or with sudo):
    apt-get install -y libatomic1
    playwright install --with-deps chromium
(libatomic1 is for Playwright's own driver: without it neither playwright command can run, and they print 'libatomic.so.1: cannot open shared object file'.)
The underlying error was: Exception: Connection closed while reading from the driver
[exit 0, 1 s]

== playwright install --with-deps chromium, as it stands

$ playwright install --with-deps chromium 2>&1 | tr '\r' '\n' | grep -v -E '^\|| [0-9]+% of|^(Get|Hit|Ign|Fetched|Selecting|Preparing|Unpacking|Setting up|Processing|\(Reading|Reading|Building)' | tail -n 12
/root/venv/lib/python3.12/site-packages/playwright/driver/node: error while loading shared libraries: libatomic.so.1: cannot open shared object file: No such file or directory
[exit 0, 0 s]

== the library Playwright's driver needs

$ apt-get install -y -qq --no-install-recommends libatomic1 > /dev/null; dpkg -s libatomic1 | grep -E '^(Package|Status|Version)'
debconf: delaying package configuration, since apt-utils is not installed
Package: libatomic1
Status: install ok installed
Version: 14.2.0-4ubuntu2~24.04.1
[exit 0, 1 s]

== playwright install chromium (alone), again

$ playwright install chromium 2>&1 | tr '\r' '\n' | grep -v -E '^\|| [0-9]+% of' | tail -n 12
Downloading Chrome for Testing 159.0.8154.6 (playwright chromium v1255) from https://cdn.playwright.dev/builds/cft/159.0.8154.6/linux64/chrome-linux64.zip
Chrome for Testing 159.0.8154.6 (playwright chromium v1255) downloaded to /root/.cache/ms-playwright/chromium-1255
Downloading FFmpeg (playwright ffmpeg v1013) from https://cdn.playwright.dev/dbazure/download/playwright/builds/ffmpeg/1013/ffmpeg-linux.zip
FFmpeg (playwright ffmpeg v1013) downloaded to /root/.cache/ms-playwright/ffmpeg-1013
Downloading Chrome Headless Shell 159.0.8154.6 (playwright chromium-headless-shell v1255) from https://cdn.playwright.dev/builds/cft/159.0.8154.6/linux64/chrome-headless-shell-linux64.zip
Chrome Headless Shell 159.0.8154.6 (playwright chromium-headless-shell v1255) downloaded to /root/.cache/ms-playwright/chromium_headless_shell-1255
[exit 0, 119 s]

$ du -sh /root/.cache/ms-playwright; ls /root/.cache/ms-playwright
700M	/root/.cache/ms-playwright
chromium-1255
chromium_headless_shell-1255
ffmpeg-1013
[exit 0, 0 s]

== does the browser start with 'playwright install chromium' alone?

$ for f in /root/.cache/ms-playwright/chromium_headless_shell-*/chrome-*/*headless*shell; do echo $f; ldd $f | grep 'not found' | sort -u; done
/root/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/LICENSE.headless_shell
	not a dynamic executable
/root/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell
	libX11.so.6 => not found
	libXcomposite.so.1 => not found
	libXdamage.so.1 => not found
	libXext.so.6 => not found
	libXfixes.so.3 => not found
	libXrandr.so.2 => not found
	libasound.so.2 => not found
	libatk-1.0.so.0 => not found
	libatk-bridge-2.0.so.0 => not found
	libatspi.so.0 => not found
	libdbus-1.so.3 => not found
	libgbm.so.1 => not found
	libgio-2.0.so.0 => not found
	libglib-2.0.so.0 => not found
	libgobject-2.0.so.0 => not found
	libnspr4.so => not found
	libnss3.so => not found
	libnssutil3.so => not found
	libxcb.so.1 => not found
	libxkbcommon.so.0 => not found
[exit 0, 0 s]

$ ai-detect --file /root/page.html 2>&1 | head -n 14
URL input needs Playwright and its Chromium build, which are not installed.
From the ai-detect folder run:
    pip install ".[web]"
    playwright install chromium
If both are installed and the browser still cannot start, the system is missing libraries it needs. On Debian or Ubuntu run (as root, or with sudo):
    apt-get install -y libatomic1
    playwright install --with-deps chromium
(libatomic1 is for Playwright's own driver: without it neither playwright command can run, and they print 'libatomic.so.1: cannot open shared object file'.)
The underlying error was: TargetClosedError: [pid=2541][err] /root/.cache/ms-playwright/chromium_headless_shell-1255/chrome-headless-shell-linux64/chrome-headless-shell: error while loading shared libraries: libglib-2.0.so.0: cannot open shared object file: No such file or directory
[exit 0, 0 s]

== playwright install --with-deps chromium

$ playwright install --with-deps chromium 2>&1 | tr '\r' '\n' | grep -v -E '^\|| [0-9]+% of|^(Get|Hit|Ign|Fetched|Selecting|Preparing|Unpacking|Setting up|Processing|\(Reading|Reading|Building)' | tail -n 14

[exit 0, 48 s]

$ for f in /root/.cache/ms-playwright/chromium_headless_shell-*/chrome-*/*headless*shell; do ldd $f | grep -c 'not found'; done
	not a dynamic executable
0
0
[exit 1, 0 s]

$ ai-detect --file /root/page.html 2>&1 | head -n 14
Loading GPTTrace Ettin-150M v5e (int8 ONNX) (ONNX)...
Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.
Model loaded via onnxruntime CPUExecutionProvider (GPTTrace Ettin-150M v5e (int8 ONNX))

  Model AI score (raw mean of sentences): 63.4% - LIKELY AI   [gpttrace-150m]
  Assessment: Uncertain (calibrated document score 54.1%, confidence low)
  Sentences: 2 AI / 2 Human / 4 scored (1 skipped <5 words)
  SDSL: mean=18.0 words, stddev=4.9, CV=0.27 (very uniform (AI-like))
  Patterns: 3 formal verb, 3 ai slop, 2 formal transition, 1 vague abstraction
  Document score (raw): 82.9% over 1 passage(s), 72 words, confidence low
  At the 5%-false-positive operating point: 2 of 4 sentences flagged, document 54.1%
  Note: Only 72 words. The model cards call results under about 150 words unreliable.
  Note: Sentence scores are split, which can mean mixed authorship or an edited draft. Single-sentence scores are a rough signal.

[exit 0, 2 s]

$ du -sh /root/venv /root/.cache/ms-playwright /root/.cache/huggingface
1.5G	/root/venv
700M	/root/.cache/ms-playwright
148M	/root/.cache/huggingface
[exit 0, 0 s]

== PART B DONE (ubuntu)
```

