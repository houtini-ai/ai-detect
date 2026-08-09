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
        line("onnxruntime", "not installed (only needed for --model light)")

    try:
        import mcp  # noqa: F401
        line("mcp", "available (MCP server ready)")
    except ImportError:
        line("mcp", "NOT INSTALLED  (pip install mcp)")

    print("-" * 40)
    print("Default model : desklib/ai-text-detector-v1.01 (~1.7 GB, first run downloads it)")
    print("Light model   : onnx-community/tmr-ai-text-detector-ONNX (~126 MB)")


if __name__ == "__main__":
    main()
