# Writer facts, 25 Nov 2026

For whoever rewrites `README.md` and the docs prose. Every row is something that changed or was newly proven on 25 Nov 2026. Nothing here is from memory: `source` is the file, command or page the row rests on, `quote` is the exact text it printed or holds, `read` is the day it was run or read.

`status` is one of: **decided** (Richard's decision), **changed** (the code or a file changed today), **proven** (run today, transcript kept), **read** (read today at the source named), **code** (true from the code as it stands; not run), **carried over** (measured or read on 24 Nov, not repeated), **untested** (not run; do not claim it works).

Transcripts: `docs/proofs/linux-venv-2026-11-25.md`, `docs/proofs/windows-venv-2026-11-25.md`. Worked-example figures: `docs/eval-data/worked-example-2026-11-25.json`.

## 1. The new default and the first run

| row | status | claim | source | quote | read |
|---|---|---|---|---|---|
| w-1 | decided | The default model is `gpttrace-150m`. It was `desklib`. | `ai_detect/models.py` | `DEFAULT_MODEL = "gpttrace-150m"` | 2026-11-25 |
| w-2 | changed | The version is still 2.0.0. Nothing has been published. The CHANGELOG 2.0.0 entry was amended and is dated 2026-11-25. | `CHANGELOG.md` | `## [2.0.0] - 2026-11-25 (prepared, not published)` | 2026-11-25 |
| w-3 | proven | A bare `ai-detect sample.txt` (no `--model`) downloads `gpttrace-150m` and scores with it. | both proof files | `Downloading GPTTrace Ettin-150M v5e (int8 ONNX) (~151 MB, one time; resumes if interrupted)...` | 2026-11-25 |
| w-4 | proven | The first-run download is announced as "~151 MB". The progress bar counts to 148 MB and the cache folder is 148 MB on disk (the bar and `du` count in units of 1024). The bar's last line reads "100.0% of 151 MB": once the model is ready it falls back to the registry's round figure. Not fixed. It was 1736 MB with `desklib`. | both proof files; `ai-detect models` | `gpttrace-150m  [##..........................]   9.5% of 148 MB less than a minute left`, `gpttrace-150m  [############################] 100.0% of 151 MB` and `148M	/root/.cache/huggingface` | 2026-11-25 |
| w-5 | proven | First scan including the download: 22 s in a `debian:12` container, 33 s on Windows 11. Second scan, model on disk: 1 s. One machine, one network; not a benchmark. | both proof files | `[exit 0, 22 s]`, `[exit 0, 33 s]`, `[exit 0, 1 s]` | 2026-11-25 |
| w-6 | changed | `desklib` is still supported and unchanged. Keep it with `--model desklib` (CLI), `"model": "desklib"` (MCP) or its tick box (dashboard). | `ai_detect/models.py`; `ai-detect models` | `desklib          1736 MB  MIT           42 of 61` | 2026-11-25 |
| w-7 | changed | `ai-detect models` marks the default on the `gpttrace-150m` line. | both proof files | `gpttrace-150m     151 MB  CC-BY-SA-4.0  4 of 61     not downloaded  GPTTrace Ettin-150M v5e (int8 ONNX) (default)` | 2026-11-25 |
| w-8 | changed | `--help` names the new default. | `ai_detect/cli.py`; `tests/test_default_model.py` | `(default: gpttrace-150m)` | 2026-11-25 |
| w-9 | changed | Every MCP tool with a `model` parameter defaults to `gpttrace-150m`; the server instructions and `list_models` say so. | `docs/FEATURES.md` section 4 (read from the running server) | `The default is gpttrace-150m.` | 2026-11-25 |
| w-10 | changed | `manifest.json` `long_description` names the default and its size. `server.json` and `package.json` did not name a default and are unchanged. | `manifest.json` | `The default model, gpttrace-150m, is a 151 MB download from Hugging Face on first use; the other five are 126 MB to 1.7 GB each.` | 2026-11-25 |
| w-11 | carried over | Why this model: 151 MB against 1.74 GB; 6.2 ms a sentence against 49.8 ms on CPU; 4th of 61 on RAID against 42nd; 8% of human passages over 0.5 against 12%; 3 of 24 casual sentences over 0.5 against 17. Its passage AUROC on the local corpus is lower: 0.969 against 0.996. At a 5% false-positive rate it caught 29% of AI sentences (desklib 17%). | `docs/MODEL-EVAL-2026-11.md` results table | `gpttrace-150m \| 1.0 \| 6.2 \| 62 \| 0.733 \| 29% \| 0.969 \| 90% \| 63% \| 8% \| 24/24 \| 3/24` | measured 2026-11-24; not re-run |
| w-12 | carried over | The `gpttrace-150m` weights are CC BY-SA 4.0 (`desklib` is MIT). ai-detect downloads them from the authors' repository and does not redistribute them. Running the model puts no condition on the user's text, the results or ai-detect's MIT code. Attribution and share-alike apply to someone who redistributes or adapts the weights. | `ai_detect/models.py`; `THIRD-PARTY-MODELS.md`; https://huggingface.co/nakas/gpttrace-ettin150-text-v5e | `Weights are CC BY-SA 4.0: attribution and share-alike apply if you redistribute or adapt the weights.` | licence read 2026-11-24; not re-read today |
| w-13 | code | Scores from `desklib` and `gpttrace-150m` are not comparable: each model has its own operating point. A scan made with the old default and one made with the new will differ. | `ai_detect/calibration.json`, sentence level, printed with Python | `gpttrace-150m {'threshold': 4.277, 'scale': 2.529}` and `desklib {'threshold': 3.31, 'scale': 1.382}` | 2026-11-25 |
| w-14 | read | GitHub `main` is at 4db3fe7, which is 2.0.0 **before** today's commits. A clone today still gets `desklib` as the default and onnxruntime as an extra. Today's commits are on the local branch `rebuild-2026-11` and are not pushed. | `git ls-remote origin main` | `4db3fe7efabee42888da8cafa402d5ae76c5352d	refs/heads/main` | 2026-11-25 |
| w-15 | not done | `scripts/eval_models.py` was not re-run. Its figures are per model and do not depend on which model is the default; `ai_detect/calibration.json` and the results file are unchanged. | `git diff 4db3fe7 -- ai_detect/calibration.json docs/eval-data/results-2026-11-24-cpu.json` | (no output) | 2026-11-25 |

## 2. Dependencies and extras

| row | status | claim | source | quote | read |
|---|---|---|---|---|---|
| w-16 | changed | `onnxruntime>=1.20` is a core dependency. `pip install .` is enough for the default model. | `pyproject.toml` | `"onnxruntime>=1.20",` | 2026-11-25 |
| w-17 | changed | A plain `pip install .` runs five of the six models: `gpttrace-150m`, `gpttrace-1b`, `light`, `desklib`, `tabularis`. Only `conpara` needs an extra (`[conpara]`: sentencepiece, protobuf). | `ai_detect/models.py` (`extra=` is set on conpara only); `docs/FEATURES.md` section 6 | `extra="conpara",` | 2026-11-25 |
| w-18 | changed | The `light` and `onnx` extras still exist and add nothing new, so `pip install ".[light]"` in older instructions does not break. | `pyproject.toml`; `tests/test_default_model.py` | `light = ["onnxruntime>=1.20"]` | 2026-11-25 |
| w-19 | changed | The `all` extra is now `conpara` plus `web`: sentencepiece, protobuf, playwright. | `pyproject.toml` | `all = ["sentencepiece>=0.2", "protobuf>=5", "playwright>=1.48"]` | 2026-11-25 |
| w-20 | changed | The `gpu-directml` extra is kept as a name and installs nothing. | `pyproject.toml` | `gpu-directml = []` | 2026-11-25 |
| w-21 | proven | Why: `onnxruntime` and `onnxruntime-directml` installed together leave only the CPU providers, in either install order. | fresh Windows venv, `pip install onnxruntime onnxruntime-directml` | `onnxruntime          1.32.0` / `onnxruntime-directml 1.24.4` / `1.32.0 ['AzureExecutionProvider', 'CPUExecutionProvider']` | 2026-11-25 |
| w-22 | proven | With both installed, `pip uninstall onnxruntime` alone breaks the package. That is why the documented swap ends with `--force-reinstall`. | same venv | `AttributeError: module 'onnxruntime' has no attribute '__version__'` | 2026-11-25 |
| w-23 | proven | With `onnxruntime-directml` as the only build installed, the DirectML provider is offered. No model was run on it. | same venv, both removed, then `pip install onnxruntime-directml` | `1.24.4 ['DmlExecutionProvider', 'CPUExecutionProvider']` | 2026-11-25 |
| w-24 | untested | After that swap pip's metadata no longer has an `onnxruntime` distribution, so `pip check` may complain and a later `pip install .` may put the CPU build back. Neither was run. | inference from w-21 to w-23 | | |
| w-25 | changed | The npm launcher no longer asks for the `light` extra. `AI_DETECT_EXTRAS` defaults to none. The MCPB `manifest.json` still passes `--extra light`, which is harmless. | `bin/launch.js`; `manifest.json` | `const extras = (process.env.AI_DETECT_EXTRAS \|\| '')` | 2026-11-25 |
| w-26 | changed | A model that needs a missing package now says `Run:  pip install <package>` when no extra provides it. | `ai_detect/backends.py` `_import` | `Run:  pip install {module}` | 2026-11-25 |

## 3. Devices: CPU fallback and the GPU routes

| row | status | claim | source | quote | read |
|---|---|---|---|---|---|
| w-27 | proven | In a plain install the default model runs on the CPU, on Windows and on Linux. The other two ONNX models (`gpttrace-1b`, `light`) take the same code path. | both proof files | `Model loaded via onnxruntime CPUExecutionProvider (GPTTrace Ettin-150M v5e (int8 ONNX))` | 2026-11-25 |
| w-28 | proven | The plain `onnxruntime` wheel offers no GPU provider on Windows or Linux. | both proof files | `onnxruntime 1.32.0 ['AzureExecutionProvider', 'CPUExecutionProvider']` | 2026-11-25 |
| w-29 | changed | A unit test covers the fallback: with no GPU provider available the provider list is CPU only, for every `--device` value. | `tests/test_default_model.py::test_onnx_providers_fall_back_to_cpu_when_no_gpu_provider` | `assert backends.onnx_providers(ort, pref) == ["CPUExecutionProvider"]` | 2026-11-25 |
| w-30 | code | GPU route for the ONNX models: replace the CPU build with `onnxruntime-directml` (Windows, DirectML) or `onnxruntime-gpu` (NVIDIA CUDA). Commands: `pip uninstall -y onnxruntime`, then `pip install --force-reinstall onnxruntime-directml` (or `onnxruntime-gpu`). ai-detect then picks `DmlExecutionProvider`, `CUDAExecutionProvider` or `ROCMExecutionProvider`, in that order, with CPU behind it. | `ai_detect/backends.py` `onnx_providers`, `ONNX_GPU_HINT` | `ONNX_GPU_PROVIDERS = ("DmlExecutionProvider", "CUDAExecutionProvider", "ROCMExecutionProvider")` | 2026-11-25 |
| w-31 | untested | No ONNX model was run on a GPU, with either GPU build. | | | |
| w-32 | changed | `--device cuda` with no GPU provider installed prints the swap commands and carries on with the CPU. If a GPU build is installed beside the CPU build, a warning says the CPU build has overwritten it. | `ai_detect/backends.py`; `tests/test_default_model.py` | `Requested GPU but no GPU execution provider is installed; using CPU.` | 2026-11-25 |
| w-33 | code | GPU route for the three PyTorch models (`desklib`, `tabularis`, `conpara`): a torch build with CUDA, and an NVIDIA GPU. With `--device auto` they use CUDA when `torch.cuda.is_available()`, else the CPU. | `ai_detect/backends.py` `resolve_torch_device` | `return torch.device("cuda" if torch.cuda.is_available() else "cpu")` | 2026-11-25 |
| w-34 | proven | On Windows, `pip install .` from PyPI gets a CPU-only torch, even on a machine with NVIDIA GPUs. A CUDA wheel has to be installed from PyTorch's own index. That install was not run today. | `docs/proofs/windows-venv-2026-11-25.md` | `torch 2.15.0+cpu cuda available: False` | 2026-11-25 |
| w-35 | proven | On Linux, `pip install .` from PyPI gets the CUDA build of torch and about 3 GB of `nvidia-*` libraries, whether or not the machine has a GPU. | `docs/proofs/linux-venv-2026-11-25.md` transcript A | `torch 2.15.0+cu132 cuda available: False` and `3.0G	/root/venv/lib/python3.11/site-packages/nvidia` | 2026-11-25 |
| w-36 | code | macOS: neither family uses the GPU. The torch path only looks for CUDA (no MPS). The ONNX path does not select CoreML. | `ai_detect/backends.py` `onnx_providers` docstring | `CoreML, which the macOS wheel` / `carries, is not selected: it is untested with these quantised models.` | 2026-11-25 |
| w-37 | untested | Nothing was run on macOS. It could not be: the work was done on one Windows machine and in Linux containers. | | | |

## 4. Platform wheels (PyPI metadata, not installs)

Read from `https://pypi.org/pypi/<name>/json` on 25 Nov 2026.

| row | status | claim | source | quote | read |
|---|---|---|---|---|---|
| w-38 | read | The pin is a floor, `onnxruntime>=1.20`. A fresh install resolved 1.32.0 on Windows, Debian 12 and Ubuntu 24.04. 1.32.0 was uploaded on 2026-11-13 and needs Python 3.11 or later. | pypi.org/pypi/onnxruntime/json; both proof files | `onnxruntime               1.32.0` | 2026-11-25 |
| w-39 | read | onnxruntime 1.32.0 wheels for CPython 3.11, 3.12, 3.13 and 3.14: Windows x64, Windows ARM64, Linux x86_64, Linux aarch64, macOS arm64. | pypi.org/pypi/onnxruntime/json | `onnxruntime-1.32.0-cp313-cp313-win_amd64.whl`, `...-win_arm64.whl`, `...-manylinux_2_28_x86_64.whl`, `...-manylinux_2_28_aarch64.whl`, `...-macosx_14_0_arm64.whl` (the same five for cp311, cp312, cp314; also free-threaded cp313t and cp314t for Linux) | 2026-11-25 |
| w-40 | read | The Linux wheels are `manylinux_2_28`: glibc 2.28 or later. The macOS wheel is `macosx_14_0_arm64`: macOS 14 or later, Apple silicon. | same | as above | 2026-11-25 |
| w-41 | read | There is no macOS x86_64 (Intel) wheel for onnxruntime 1.24.1 or later. The last release with one is 1.23.2 (`macosx_13_0_x86_64`, cp310 to cp313), which the `>=1.20` floor still allows. | pypi.org/pypi/onnxruntime/json, every release | `onnxruntime-1.23.2-cp313-cp313-macosx_13_0_x86_64.whl` | 2026-11-25 |
| w-42 | read | torch is the tighter limit on Intel Macs: the last torch release with a macOS x86_64 wheel is 2.2.2, and ai-detect needs `torch>=2.6`. So an Intel Mac has no torch wheel to install. This is from metadata; it was not tried. | pypi.org/pypi/torch/json; `pyproject.toml` | `last torch with macOS x86_64 wheel: 2.2.2` (computed from the release list) | 2026-11-25 |
| w-43 | read | torch 2.15.0 has wheels for Windows x64, Linux x86_64, Linux aarch64 and macOS arm64 (`macosx_14_0_arm64`), CPython 3.11 to 3.15. There is no Windows ARM64 torch wheel on PyPI. | pypi.org/pypi/torch/json | `torch-2.15.0-cp313-cp313-macosx_14_0_arm64.whl`, `...-manylinux_2_28_aarch64.whl`, `...-manylinux_2_28_x86_64.whl`, `...-win_amd64.whl` | 2026-11-25 |
| w-44 | untested | macOS arm64 and Linux aarch64: the wheels exist, so the install should resolve. Neither platform was run. Do not write that they were tested. | w-39, w-43 | | |
| w-45 | read | GPU builds: `onnxruntime-directml` latest is 1.24.4 (2026-03-17), Windows x64 only, CPython 3.11 to 3.14. `onnxruntime-gpu` latest is 1.32.0: Windows x64, Linux x86_64, Linux aarch64. | pypi.org/pypi/onnxruntime-directml/json, onnxruntime-gpu/json | `onnxruntime_directml-1.24.4-cp313-cp313-win_amd64.whl`; `onnxruntime_gpu-1.32.0-cp313-cp313-manylinux_2_28_x86_64.whl` | 2026-11-25 |
| w-46 | proven | Python versions actually run today: 3.13.2 (Windows 11), 3.11.2 (Debian 12), 3.12.3 (Ubuntu 24.04). | both proof files | `Python 3.11.2`, `Python 3.12.3`, `Python 3.13.2` | 2026-11-25 |

## 5. Linux: the venv route and the no-venv error

All in `docs/proofs/linux-venv-2026-11-25.md`. Containers: `debian:12`, `debian:12-slim`, `ubuntu:24.04`, each new, nothing mounted, code from a git bundle.

| row | status | claim | source | quote | read |
|---|---|---|---|---|---|
| w-47 | proven | Packages installed first: `python3 python3-venv python3-pip git ca-certificates`. | transcripts A and B1 | `apt-get update -qq && apt-get install -y -qq --no-install-recommends python3 python3-venv python3-pip git ca-certificates` | 2026-11-25 |
| w-48 | proven | Without a virtual environment `pip install .` is refused on Debian 12 and Ubuntu 24.04. `python3 -m pip install .` is refused the same way. | transcript A | `error: externally-managed-environment` then `× This environment is externally managed` then `╰─> To install Python packages system-wide, try apt install` | 2026-11-25 |
| w-49 | proven | The message itself gives the fix. | transcript A | `create a virtual environment using python3 -m venv path/to/venv.` and `See /usr/share/doc/python3.11/README.venv for more information.` | 2026-11-25 |
| w-50 | proven | The route that works: `python3 -m venv <dir>`, `. <dir>/bin/activate`, `pip install .`, `ai-detect --version`, `ai-detect sample.txt`. | transcript A | `ai-detect 2.0.0` | 2026-11-25 |
| w-51 | proven | From the default index that install took 432 s and the venv is 5.7 GB (3.0 GB `nvidia-*`, 1.2 GB torch, 78 MB onnxruntime). | transcript A | `[exit 0, 432 s]` and `5.7G	/root/venv` | 2026-11-25 |
| w-52 | proven | CPU-only PyTorch in one command: `pip install . --extra-index-url https://download.pytorch.org/whl/cpu`. Venv 1.3 to 1.4 GB, 69 to 131 s, no `nvidia-*` packages. Works with the distro pip on all three images. | transcripts B1 to B3 | `torch                     2.15.0+cpu` and `1.4G	/root/venv` | 2026-11-25 |
| w-53 | proven | The usual two-step form, `pip install torch --index-url https://download.pytorch.org/whl/cpu` first, **fails on Debian 12** with its pip 23.0.1. It works on Ubuntu 24.04 with pip 24.0. | transcripts B1, B3 | `has inconsistent Name: expected 'typing-extensions', but metadata has 'typing_extensions'` then `ERROR: No matching distribution found for flit_core<4,>=3.11` | 2026-11-25 |
| w-54 | proven (by hand) | On Debian 12 the two-step form works after `pip install --upgrade pip` inside the venv (pip 26.3; 40 s; venv 955 MB with torch alone). Run by hand in the first container; not in a saved transcript. | hand run, 25 Nov 2026 | `Successfully installed ... torch-2.15.0+cpu typing-extensions-4.16.0` | 2026-11-25 |
| w-55 | proven | The same text and model gave the same scores in every container and on Windows. | all transcripts | `Assessment: Uncertain (calibrated document score 54.1%, confidence low)` | 2026-11-25 |
| w-56 | proven | huggingface_hub prints a warning about unauthenticated requests on every run. It does not stop anything. | all transcripts | `Warning: You are sending unauthenticated requests to the HF Hub. Please set a HF_TOKEN to enable higher rate limits and faster downloads.` | 2026-11-25 |

## 6. Playwright on Linux: stock and slim images

| row | status | claim | source | quote | read |
|---|---|---|---|---|---|
| w-57 | proven | `pip install ".[web]"` works (playwright 1.65.2, 20 to 23 s). | transcripts B1 to B3 | `Successfully installed ai-detect-2.0.0 greenlet-3.5.6 playwright-1.65.2` | 2026-11-25 |
| w-58 | proven | Straight after that, `playwright install chromium` does **not** work on `debian:12`, `debian:12-slim` or `ubuntu:24.04`. Playwright's bundled Node needs `libatomic.so.1`. It prints one line and downloads nothing. | transcripts B1 to B3 | `.../playwright/driver/node: error while loading shared libraries: libatomic.so.1: cannot open shared object file: No such file or directory` | 2026-11-25 |
| w-59 | proven | `playwright install --with-deps chromium` fails the same way at that point, for the same reason: the installer is run by that Node. | transcripts B1 to B3 | same line | 2026-11-25 |
| w-60 | proven | `apt-get install -y libatomic1` fixes the driver (Debian 12: 12.2.0-14+deb12u1; Ubuntu 24.04: 14.2.0-4ubuntu2~24.04.1). | transcripts B1 to B3 | `Package: libatomic1` / `Status: install ok installed` | 2026-11-25 |
| w-61 | proven | After that, `playwright install chromium` alone downloads the browser (700 MB in `~/.cache/ms-playwright`, 108 to 136 s) but the browser cannot start: 20 shared libraries are missing, on all three images. | transcripts B1 to B3 | `libglib-2.0.so.0 => not found`, `libnss3.so => not found`, `libX11.so.6 => not found` (20 lines) | 2026-11-25 |
| w-62 | proven | `playwright install --with-deps chromium` then installs them (34 to 48 s, as root) and an `.html` scan works. | transcripts B1 to B3 | `Model AI score (raw mean of sentences): 63.4% - LIKELY AI   [gpttrace-150m]` after the `--with-deps` step | 2026-11-25 |
| w-63 | proven | Stock against slim: no difference. The stock `debian:12` image, the slim one and `ubuntu:24.04` each needed all three steps (w-60, the browser download, `--with-deps`). A desktop Linux install that already has a browser's libraries was not tried. | transcripts B1 to B3 | see w-58 to w-62 | 2026-11-25 |
| w-64 | changed | What ai-detect prints when Playwright is installed but cannot start: the install message, the two Debian/Ubuntu commands, and the underlying error line. No traceback. | `ai_detect/fetch.py`; transcripts B1 to B3 | `The underlying error was: Exception: Connection closed while reading from the driver` (driver) and `The underlying error was: TargetClosedError: ... chrome-headless-shell: error while loading shared libraries: libglib-2.0.so.0: cannot open shared object file` (browser) | 2026-11-25 |
| w-65 | proven | Without the `[web]` extra the message is the two install commands only, exit code 1. | transcripts B1 to B3 | `URL input needs Playwright and its Chromium build, which are not installed.` | 2026-11-25 |
| w-66 | proven | Sizes after everything (CPU-only torch, `[web]`, Chromium, default model): venv 1.5 GB, Playwright cache 700 MB, model cache 148 MB. | transcripts B1 to B3 | `1.5G	/root/venv` / `700M	/root/.cache/ms-playwright` / `148M	/root/.cache/huggingface` | 2026-11-25 |
| w-67 | untested | `playwright install chromium` on Windows and macOS was not run today. On this Windows machine Playwright and Chromium were already installed. | | | |

## 7. Windows: fresh venv and the full-path MCP command

All in `docs/proofs/windows-venv-2026-11-25.md`. Windows 11 Pro, Python 3.13.2, Node 24.6.0.

| row | status | claim | source | quote | read |
|---|---|---|---|---|---|
| w-68 | proven | `python -m venv .venv`, `.\.venv\Scripts\Activate.ps1`, `pip install .` with no extras works in 75 s. The venv is 938 MB. | transcript 1 | `Successfully built ai-detect` and `938 MB` | 2026-11-25 |
| w-69 | proven | Resolved versions: torch 2.15.0 (+cpu), onnxruntime 1.32.0, transformers 5.24.1, tokenizers 0.23.3, huggingface_hub 2.4.0, mcp 2.3.0, numpy 2.5.5. So the fresh install ran on MCP SDK 2.x. | transcript 1 | `mcp                       2.3.0` | 2026-11-25 |
| w-70 | proven | The clone sat under a user folder whose name contains a space. Install, scan and the MCP server all worked from it. | transcript 1 | `C:\Users\<user>\ai-detect-proof\ai-detect\.venv` | 2026-11-25 |
| w-71 | proven | The MCP server starts from its full path with the venv not activated. | transcript 1 | `initialize ok: ai-detect 2.0.0, protocol 2025-06-18, instructions 1045 chars` then `SMOKE PASS` | 2026-11-25 |
| w-72 | proven | It lists 9 tools and scans with the default model when no `model` is given. | transcript 1 | `scan ok: model gpttrace-150m, sentence score 63.4%, document 23.8%, sentences 2, dashboard http://127.0.0.1:8765/#/scan/20261125-065158-e15688` | 2026-11-25 |
| w-73 | proven | The exact JSON that worked. Every backslash is doubled. | transcript 2 | see the block below the table | 2026-11-25 |
| w-74 | proven | The same file with single backslashes is not valid JSON. | transcript 2 | `JSON error: Bad escaped character in JSON at position 60 (line 4 column 22)` | 2026-11-25 |
| w-75 | untested | The config was not loaded into Claude Desktop or Claude Code. The proof starts the command the way a client does: the command alone, no shell, pipes for input and output. | `scripts/smoke_mcp.mjs` | `const child = spawn(command, args, { stdio: ['pipe', 'pipe', 'inherit'],` | 2026-11-25 |
| w-76 | proven | On Windows huggingface_hub also warns once that its cache cannot use symlinks without Developer Mode. The download still completes. | transcript 1 | `To support symlinks on Windows, you either need to activate Developer Mode or to run Python as an administrator.` | 2026-11-25 |

```json
{
  "mcpServers": {
    "ai-detect": {
      "command": "C:\\Users\\<user>\\ai-detect-proof\\ai-detect\\.venv\\Scripts\\ai-detect-mcp.exe"
    }
  }
}
```

## 8. History and the command line

| row | status | claim | source | quote | read |
|---|---|---|---|---|---|
| w-77 | code | The docs were wrong and the code is right: the command line does not save scans. Only scans made through the dashboard or the MCP server are saved to history. Behaviour was not changed. | `ai_detect/web/app.py` `run_scan` (the only caller of `history.save`); `ai_detect/cli.py` (never calls it) | `scan_id = history.save(report, loaded.screenshot)` | 2026-11-25 |
| w-78 | proven | After two command-line scans nothing exists in the data folder. | both proof files | Linux: `ls: cannot access '/root/.ai-detect': No such file or directory`. Windows: `Test-Path $env:AI_DETECT_HOME` gives `False` | 2026-11-25 |
| w-79 | proven | After one MCP scan the data folder holds the scan and the engine log. | `docs/proofs/windows-venv-2026-11-25.md` transcript 1 | `history` / `engine.log` / `history\20261125-065158-e15688.json` | 2026-11-25 |
| w-80 | changed | `ai-detect --help` now says so, and two tests pin it. | `ai_detect/cli.py`; `tests/test_doc_fixes.py` | `The command line does not save scans: nothing is written unless --export names a file.` | 2026-11-25 |
| w-81 | code | To keep a command-line result, use `--export report.html` (or `.csv`, `.json`) or `--json`. | `ai_detect/cli.py` | `--export needs a .html, .csv or .json file name` | 2026-11-25 |

## 9. One verdict, one figure

| row | status | claim | source | quote | read |
|---|---|---|---|---|---|
| w-82 | changed | The History and Batch tables show the calibrated document score in the Document column: the same figure and verdict as the result page. | `ai_detect/history.py`, `ai_detect/web/static/app.js`; `tests/ui/test_dashboard.py::test_history_document_column_is_the_result_pages_figure`; `docs/screenshots/history-light.png` | `Likely human` / `6.3%` on the History row and on the result page of the same scan | 2026-11-25 |
| w-83 | changed | In those tables the Sentences column is a raw mean when one model ran, and is marked `raw`. For an ensemble it is the mean of the calibrated values and is not marked. | same; `docs/screenshots/history-light.png` | `61.5% raw` | 2026-11-25 |
| w-84 | changed | The Compare table's Verdict row repeats the two cards ("Likely AI", "Uncertain", "Likely human"). The capitalised 1.0.0 words no longer appear there. | `ai_detect/analyze.py` `compare`; `tests/ui/test_dashboard.py::test_compare_shows_delta_table`; `docs/screenshots/compare-light.png` | `Verdict  Likely AI  Uncertain` | 2026-11-25 |
| w-85 | changed | Compare table rows now: Verdict; Document score (calibrated); Sentences flagged (at the operating point); then for a single model "Document score, raw", "Mean sentence score, raw", "Sentences over 50%, raw", or for an ensemble "Mean sentence score"; Sentence pattern hits; Structure and style tells. | `ai_detect/web/static/app.js` | `Document score, raw` | 2026-11-25 |
| w-86 | changed | The compare result (CLI `--compare`, MCP `compare_texts` under `change`, dashboard) has new keys `calibrated_document_pct`, `delta_calibrated_document_pct`, `operating_point_flagged`, `raw_scale`; `verdicts` holds the assessment labels. `document_ai_pct`, `sentence_ai_pct`, `flagged_sentences`, `delta_ai_pct` are unchanged. | `ai_detect/analyze.py` | `"verdicts": [label(report_a), label(report_b)],` | 2026-11-25 |
| w-87 | changed | History and batch rows, and the batch CSV, have two new fields: `calibrated_document_pct` and `raw_scale`. | `ai_detect/history.py`, `ai_detect/report.py` | `keys = ["label", "verdict", "confidence", "calibrated_document_pct", "document_ai_pct",` | 2026-11-25 |
| w-88 | changed | The CLI prints an `Assessment:` line and labels the single-model figures raw. | both proof files; `docs/FEATURES.md` section 3 | `Model AI score (raw mean of sentences): 63.4% - LIKELY AI   [gpttrace-150m]` / `Assessment: Uncertain (calibrated document score 54.1%, confidence low)` / `Document score (raw): 82.9% over 1 passage(s), 72 words, confidence low` | 2026-11-25 |
| w-89 | changed | The CLI batch table's `document` column is the calibrated document score, and a legend line says so. | `docs/FEATURES.md` section 3 | `document = calibrated document score; sentences = mean sentence score (raw when one model ran)` then `55.3%      98.6%        5      3  Uncertain      examples/ai-sample.txt` | 2026-11-25 |
| w-90 | changed | The exported HTML report shows the calibrated document score, with a separate labelled raw line for a single-model scan. | `ai_detect/report.py`; `tests/test_doc_fixes.py` | `Document score, raw (the probability the model itself ` | 2026-11-25 |
| w-91 | code | Raw figures that remain under their 1.0.0 names, for compatibility: in the JSON report `model_ai_pct`, `document_ai_pct` and per-sentence `ai_prob`/`label` are raw for a single model; the MCP detect result's `verdict` (`LIKELY AI`, `MIXED`, `LIKELY HUMAN`) is read from the raw sentence mean, and the CLI's first line prints the same words. The calibrated verdict is `assessment.label`. So one scan can print "LIKELY AI" on the first line and "Assessment: Uncertain" on the second (see w-88). Whether to keep the 1.0.0 words is a decision for Richard. | `ai_detect/server.py` `_summarise`; `ai_detect/cli.py` | `"verdict": _verdict(data["model_ai_pct"]),` | 2026-11-25 |
| w-92 | changed | Time left: under 45 seconds the message says "less than a minute left", otherwise the nearest whole minute. Same wording in the MCP status message, the CLI progress bar and the dashboard. | `ai_detect/downloads.py` `eta_text`; `tests/test_doc_fixes.py` | `gpttrace-150m  [#...........................]   6.8% of 148 MB less than a minute left` | 2026-11-25 |
| w-93 | proven | The first progress tick of a download can show a very large estimate before any speed is known. Not fixed. | `docs/proofs/linux-venv-2026-11-25.md` transcript A | `0.0% of 148 MB about 139 min left` | 2026-11-25 |

## 10. Screenshots, diagrams and the worked example

| row | status | claim | source | quote | read |
|---|---|---|---|---|---|
| w-94 | changed | All 25 screenshots in `docs/screenshots/` were regenerated on 25 Nov 2026 at version 2.0.0, on CPU. They show `v2.0.0`, port 8765 and the folder `C:\ai-detect-demo\history`. No temp path, no user folder. Checked by eye: `history-light.png`, `compare-light.png`, `result-single-model-light.png`. | `scripts/make_screenshots.py`; the PNG files | `C:\ai-detect-demo\history` and `http://127.0.0.1:8765` | 2026-11-25 |
| w-95 | decided | The worked example is now `https://theaiengineer.substack.com/p/how-deepseek-distilled-r1` (Richard's choice). It replaces the XDA Developers article in the script, the screenshots, `MODEL-EVAL`, `HOW-IT-WORKS` and `FEATURES`. | `scripts/make_screenshots.py` | `WORKED_EXAMPLE_URL = "https://theaiengineer.substack.com/p/how-deepseek-distilled-r1"` | 2026-11-25 |
| w-96 | proven | The page was fetched with the tool's own Playwright fetch. No sign-in, nothing clicked. There was no paywall over the article: the page showed a cookie bar and an inline subscribe box, and the article text was in the page. | the fetched page's screenshot; `docs/screenshots/page-view-annotated-light.png` | HTTP 200, page height 11476 px | 2026-11-25 |
| w-97 | changed | The first fetch read no text at all. That was a bug in ai-detect's page extractor, not the site blocking it: see the two extractor fixes in the CHANGELOG. After the fix the same fetch read the article. | `ai_detect/assets/extract.js`; `tests/ui/test_extract.py` | `UrlFetchError: No readable article text found at https://theaiengineer.substack.com/p/how-deepseek-distilled-r1 (HTTP 200).` (before) | 2026-11-25 |
| w-98 | proven | What was scanned: 2,064 words, 151 scored sentences, 17 passages. That includes page furniture the extractor kept: a course banner near the top, and after the article its footnotes, a subscribe heading, a byline line, a comments heading, three related-post titles and a closing heading. | `docs/eval-data/worked-example-2026-11-25.json` | `"words": 2064,` / `"sentences_scored": 151,` / `"passages": 17,` | 2026-11-25 |
| w-99 | proven | Default model alone (`gpttrace-150m`): verdict "Likely human", calibrated document score 6.3%, confidence high, 11 of 151 sentences flagged at the operating point. Raw: document 8.0%, mean sentence score 61.5%, 93 sentences over 0.5. Word breakdown 2% AI, 8% uncertain, 90% human. | same file, `single` | `"label": "Likely human",` / `"ai_pct": 6.3,` / `"confidence": "high",` | 2026-11-25 |
| w-100 | proven | Five-model ensemble (`gpttrace-150m`, `desklib`, `gpttrace-1b`, `tabularis`, `light`): verdict "Likely human", calibrated document score 13.7%, confidence high, note "All 5 models agree.", 1 of 151 sentences flagged. Word breakdown 0% AI, 7% uncertain, 93% human. | same file, `ensemble` | `"ai_pct": 13.7,` / `"All 5 models agree."` | 2026-11-25 |
| w-101 | proven | Per model in the ensemble run, raw document score / raw mean sentence score / sentences over raw 0.5 / sentences over its own threshold: gpttrace-150m 8.0% / 61.5% / 93 / 11; desklib 4.6% / 51.7% / 74 / 3; gpttrace-1b 89.5% / 66.4% / 100 / 21; tabularis 0.8% / 61.0% / 100 / 9; light 9.5% / 65.2% / 109 / 0. No model calls the document AI. | same file, `ensemble.per_model` | `"document_ai_pct": 89.5,` / `"document_flag": false,` (gpttrace-1b) | 2026-11-25 |
| w-102 | proven | Tells: 11 structure and style tells (4 stock vocabulary, 7 Title Case headings). Visual tells: none. | same file | `"id": "title_case_heading",` (7 times), `"id": "stock_vocabulary",` (4 times), `"visual_tells": [],` | 2026-11-25 |
| w-103 | proven | GPT-2 perplexity (ensemble run): document 238.0, per-sentence mean 352.6, burstiness 320.9, CV 0.91. | same file | `"document": 238.0,` / `"mean": 352.6,` / `"burstiness": 320.9,` / `"burstiness_cv": 0.91,` | 2026-11-25 |
| w-104 | changed | The old example's lesson no longer holds for the new one. Before: one model alone "Likely AI", five together "Uncertain". Now: both runs "Likely human" with high confidence. What the new example does show is the spread of raw figures under one verdict: raw document scores from 0.8% to 89.5%, and 74 to 109 of 151 sentences over each model's raw 0.5. | w-99 to w-101 | | 2026-11-25 |
| w-105 | rule | The example shows what the tool printed for one page on one day. It is not a finding about the article or its author. The author is not named in captions or docs. The screenshots show page text as any result screenshot does. The page's own byline is part of the fetched page, so it is visible in the page-view screenshots. | coordinator's instruction, 25 Nov 2026 | | |
| w-106 | changed | `docs/diagrams/result-anatomy.svg` and `.png`: the model list in the schematic is now `gpttrace-150m`, `gpttrace-1b`, `conpara` (it listed `desklib`), and the score reads 54% (it read 51.9%, the old example's figure). The figures in the schematic are illustrative, not from a scan. `pipeline.svg` names no model and no example and is unchanged. | the SVG | `<text x="436" y="256">gpttrace-150m</text>` | 2026-11-25 |
| w-107 | changed | Captions in `docs/FEATURES.md` section 11 changed with the pictures: the single-model result is "the default, gpttrace-150m"; the ensemble caption no longer says the models disagree. | `scripts/build_features_doc.py` | `Result of a single-model scan (the default, gpttrace-150m): verdict, highlighted text, sentence detail` | 2026-11-25 |
| w-108 | changed | The Compare screenshot is the five-model ensemble on the two bundled examples: "Likely AI" 83.6% against "Uncertain" 58.2%. | `docs/screenshots/compare-light.png` | `Likely AI` `83.6%` / `Uncertain` `58.2%` | 2026-11-25 |

## 11. Tests and generated files

| row | status | claim | source | quote | read |
|---|---|---|---|---|---|
| w-109 | proven | Test counts: 255 unit tests, 44 browser tests. (README says 125 and 29.) | `pytest`; `docs/FEATURES.md` section 12 | `255 passed` and `44 passed` | 2026-11-25 |
| w-110 | changed | `docs/FEATURES.md` was regenerated from `docs/features.template.md` on 25 Nov 2026. Its command output is today's. The template no longer says the branch is local only, that the clone fetches old code, or that the screenshots show `2.0.0.dev0`. | `scripts/build_features_doc.py` | `wrote docs/FEATURES.md` | 2026-11-25 |
| w-111 | changed | In the FEATURES tool table `list_models` is "May start a download: no". The builder used to read a wrapped docstring wrongly. | `docs/FEATURES.md` section 4 | `\| `list_models` \| none \| yes \| no \|` | 2026-11-25 |
| w-112 | changed | `scripts/smoke_mcp.mjs` scans with the server's default model unless `SMOKE_MODEL` is set (it used `light`). | the script | `const MODEL = process.env.SMOKE_MODEL \|\| '';` | 2026-11-25 |

## 12. Sentences that are now false or stale

Not rewritten. Line numbers are for the files as committed with this document. `README.md` is unchanged since 24ad54e.

### README.md

| # | line | the sentence (or the part that is wrong) | what is true |
|---|---|---|---|
| s-1 | 11 | image alt: `the verdict "Uncertain", a document score of 51.9% with low confidence, 1 of 39 sentences flagged` | The picture now shows "Likely human", 13.7%, confidence high, 1 of 151 flagged (w-100) |
| s-2 | 13 | `That's a five-model scan of one web page, made on 24 Nov 2026.` | Made on 25 Nov 2026 |
| s-3 | 61 | `pip install .                 # core: torch, transformers, mcp, starlette, uvicorn` | The core now includes onnxruntime (w-16) |
| s-4 | 62 | `pip install ".[light]"        # + onnxruntime: needed by light, gpttrace-150m, gpttrace-1b` | Not needed. The extra is an alias that adds nothing (w-18) |
| s-5 | 64 | `playwright install chromium   # once, after the [web] extra` | Not enough on Debian and Ubuntu images: `libatomic1` first, and `--with-deps` (w-58 to w-63) |
| s-6 | 73 | `(none) ... The desklib and tabularis models, the CLI, the MCP server, the dashboard` | The plain install runs five models: gpttrace-150m, gpttrace-1b, light, desklib, tabularis (w-17) |
| s-7 | 74 | `light (alias onnx) \| onnxruntime \| The light, gpttrace-150m and gpttrace-1b models` | Those models need no extra (w-17, w-18) |
| s-8 | 77 | `gpu-directml \| A DirectML GPU runtime \| Optional. Not run in this work` | The extra installs nothing now (w-20 to w-23). The GPU route is a swap of the onnxruntime build (w-30) |
| s-9 | 78 | `all \| Everything above` | `all` is conpara plus web (w-19) |
| s-10 | 83 | `A plain pip install . into a new virtual environment was not run separately.` | It was run on 25 Nov 2026 on Windows 11 and in Debian and Ubuntu containers (sections 5 and 7) |
| s-11 | 93 | `desklib (the default) \| 1736 MB \| First scan with the default model` | The default is gpttrace-150m, 151 MB. desklib downloads on first use of `--model desklib` |
| s-12 | 95 | `gpttrace-150m \| 151 MB \| First scan with --model gpttrace-150m` | First scan with the default model |
| s-13 | 111 | `ai-detect download desklib` (the first example of fetching ahead) | Still valid, but it is no longer the default model's name |
| s-14 | 134 | `they were taken while the version string still read 2.0.0.dev0.` | Regenerated at 2.0.0 (w-94) |
| s-15 | 134 | `The worked example in them is an XDA Developers article, scanned on 24 Nov 2026.` | A Substack article, scanned on 25 Nov 2026 (w-95) |
| s-16 | 153 | image alt: `Result of a single-model scan with desklib` | The single-model scan is gpttrace-150m (w-99) |
| s-17 | 187 | image alt: `the models disagree, so the verdict is Uncertain` | All five agree; the verdict is "Likely human" (w-100) |
| s-18 | 193 | `a table: document score, mean sentence score, sentences over 50%, pattern hits, tells and verdict` | The rows changed (w-85) |
| s-19 | 203 | `Every scan, newest first.` | Every scan made through the dashboard or the MCP server. Command-line scans are not saved (w-77) |
| s-20 | 233 | `Default desklib` | Default `gpttrace-150m` |
| s-21 | 235 | `Default auto: GPU if available` | For the ONNX models (which include the default) a GPU is used only with a GPU build of ONNX Runtime; a plain install runs them on the CPU (w-27 to w-30). For the torch models: CUDA if the torch build has it (w-33, w-34) |
| s-22 | 246 | `It was produced on 24 Nov 2026` | The examples that follow are older than the code. Today's output is in `docs/FEATURES.md` section 3 |
| s-23 | 256 to 258 | `desklib ... (default)` in the `ai-detect models` output; no mark on gpttrace-150m | `(default)` is on the gpttrace-150m line (w-7) |
| s-24 | 270 to 277 | the ensemble example output | An `Assessment:` line is now printed after the first line (w-88). Re-take from `docs/FEATURES.md` |
| s-25 | 299 to 305 | batch output: `98.8%      98.6% ...` and `Uncertain, document 98.8%` | The document column is calibrated now: 55.3% and 44.3%, and a legend line is printed (w-89) |
| s-26 | 310 | `The percentages in that table are raw. The verdict comes from the calibrated document score, which was 55.3% and 44.3%` | The document column is the calibrated score. Only the sentences column is raw for a single model |
| s-27 | 391 | `They were not loaded into either client during this work.` | Still true. New: the full-path form was proven with the smoke script (w-71 to w-75) |
| s-28 | 397 to 404 | `model ("desklib")` in seven rows of the tools table | `model ("gpttrace-150m")` (w-9) |
| s-29 | 455 | `The default is desklib, and that hasn't changed from 1.0.0.` | The default is gpttrace-150m and it has changed from 1.0.0 |
| s-30 | 459 | `desklib **default**` in the models table | The default mark belongs on gpttrace-150m |
| s-31 | 460 to 462 | `[light] extra` in the Needs column for light, gpttrace-150m, gpttrace-1b | core install (w-17) |
| s-32 | 484 | `the best model caught 42% of AI sentences, and the default caught 17%` | 17% was desklib. The default, gpttrace-150m, caught 29% (w-11) |
| s-33 | 531 | `So why is desklib still the default? Because I haven't changed it yet. ... Until then, if you have the [light] extra installed, --model gpttrace-150m is where I'd start.` | The whole paragraph. The default was changed on 25 Nov 2026 |
| s-34 | 551 | `Here's what that looks like on one web page, an XDA Developers article fetched once on 24 Nov 2026. It was 720 words in 39 scored sentences and 6 passages.` | The example is a Substack article, 25 Nov 2026: 2,064 words, 151 scored sentences, 17 passages (w-98) |
| s-35 | 555 to 556 | the table: `desklib alone \| Likely AI \| 76.4% ...` and `Five-model ensemble \| Uncertain \| 51.9%` | gpttrace-150m alone: Likely human, 6.3%, high, 11 of 151. Ensemble: Likely human, 13.7%, high, 1 of 151 (w-99, w-100) |
| s-36 | 558 | `One model run alone printed "Likely AI". Five together printed "Uncertain" with low confidence, because the raw document scores ran from 20% to 99%.` | Both runs printed "Likely human". Raw document scores ran from 0.8% to 89.5% (w-104) |
| s-37 | 619 | `You need the [web] extra and playwright install chromium.` | On Debian and Ubuntu images that is not enough (w-58 to w-63) |
| s-38 | 655 | `Every scan is stored as JSON, plus a JPEG for URL scans, in ~/.ai-detect/history.` | Every dashboard and MCP scan. Not command-line scans (w-77 to w-79) |
| s-39 | 690 | `No GPU run in this work. --device cuda is untested for the new models.` | Still true, and the two GPU builds of ONNX Runtime are untested too (w-31). macOS is untested (w-37) |
| s-40 | 700 | `The screenshots in docs/screenshots/ were taken while the version string still read 2.0.0.dev0.` | Regenerated at 2.0.0 (w-94) |
| s-41 | 705 | `The three that affect an existing install: the Python floor rises from 3.9 to 3.11, the MCP server now runs detection in a second process, and get_model_status gains states it did not have before.` | Four: the default model changed too. And an existing `[gpu-directml]` install loses its GPU provider (w-20, w-21) |
| s-42 | 717 | `AI_DETECT_EXTRAS ... (default light)` | Default none (w-25) |
| s-43 | 725 to 726 | `# 125 tests` and `# 29 browser tests` | 255 and 44 (w-109) |
| s-44 | 730 to 731 | `The 125 tests need no model` and `The 29 browser tests` | 255 and 44 |

### docs/RELEASE.md

| # | line | the sentence | what is true |
|---|---|---|---|
| s-45 | 21 | `The README is still the 1.0.0 text with factual corrections only.` | The README was rewritten for 2.0.0 in commit 24ad54e |
| s-46 | 22 | `The code is on a local branch in a second working folder` | GitHub `main` holds 2.0.0 as of 4db3fe7. Today's commits are local (w-14) |
| s-47 | 24 | `The default model is unchanged (desklib). Changing it is a separate decision and a separate release.` | The default is gpttrace-150m, inside 2.0.0 (w-1, w-2) |
| s-48 | 125 | `125 passed` | 255 |
| s-49 | 151 | `without it the default Linux wheel pulls several GB of CUDA libraries (not tested)` | Tested: a 5.7 GB venv, 3.0 GB of it `nvidia-*` (w-51) |
| s-50 | 159 | `bin/launch.js runs uv tool run --from <package folder>[light] ai-detect-mcp` | It passes no extra unless `AI_DETECT_EXTRAS` is set (w-25) |

### Other files

| # | file and line | the sentence | what is true |
|---|---|---|---|
| s-51 | `docs/UX-REVIEW-2026-11.md` 3 | `one of the 29 browser tests in tests/ui/test_dashboard.py` | 44 browser tests, in three files |
| s-52 | `docs/detection-patterns.md` 10 | `Model: desklib/ai-text-detector-v1.01` | Still what the page measured. But the page is written against a model that is no longer the default, and its figures did not reproduce (the notice at its top says so) |
| s-53 | `docs/MODEL-EVAL-2026-11.md` 160 | `If the default is to change, the evidence here points to gpttrace-150m` | Kept as written on 24 Nov, under a line saying the decision was made on 25 Nov. A writer may want to recast the section |
| s-54 | `docs/MODEL-EVAL-2026-11.md` 3 | `Everything here was run on 24 Nov 2026` | True of the measurements. The worked-example section is from 25 Nov 2026 and says so |
| s-55 | `docs/REVIEW-2026-11.md` 43 | `--model light without the [light] extra dies with a raw ModuleNotFoundError` | Historical. onnxruntime is a core dependency now |

Sentences that mention the XDA article: s-15, s-34 (with its table and conclusion, s-35 and s-36). No file other than `README.md` mentions it any more.
