#!/usr/bin/env python3
"""
Backwards-compatible entry point.

The implementation now lives in the `ai_detect` package. This shim keeps the
old `python detect.py ...` invocation working. Prefer the installed console
script `ai-detect` after `pip install .`.
"""

import sys

from ai_detect.cli import main

if __name__ == "__main__":
    sys.exit(main())
