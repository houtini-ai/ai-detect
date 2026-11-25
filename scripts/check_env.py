#!/usr/bin/env python3
"""
Environment doctor for ai-detect.

Reports Python, PyTorch/CUDA, Transformers, ONNX Runtime and MCP availability
so install issues are easy to diagnose.

    python scripts/check_env.py
"""

import sys


def line(label, value):
    print(f"  {label:22} {value}")


def main():
    print("ai-detect environment check")
    print("-" * 40)
    line("Python", sys.version.split()[0])
    line("Executable", sys.executable)

    try:
        import torch
        line("torch", torch.__version__)
        line("CUDA available", torch.cuda.is_available())
        if torch.cuda.is_available():
            line("GPU", torch.cuda.get_device_name(0))
    except ImportError:
        line("torch", "NOT INSTALLED  (pip install torch)")

    try:
        import transformers
        line("transformers", transformers.__version__)
    except ImportError:
        line("transformers", "NOT INSTALLED  (pip install transformers)")

    try:
        import onnxruntime as ort
        line("onnxruntime", f"{ort.__version__}  providers={ort.get_available_providers()}")
    except ImportError:
        line("onnxruntime", "NOT INSTALLED  (pip install onnxruntime; the default model needs it)")

    try:
        import mcp  # noqa: F401
        line("mcp", "available (MCP server ready)")
    except ImportError:
        line("mcp", "NOT INSTALLED  (pip install mcp)")

    print("-" * 40)
    try:
        import playwright  # noqa: F401
        line("playwright", "available (URL input)")
    except ImportError:
        line("playwright", "not installed (only needed for URL input)")
    print("-" * 40)
    print("Models: run `ai-detect models` for sizes, licences and download state.")

if __name__ == "__main__":
    main()
