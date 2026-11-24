"""ai-detect — local, per-sentence AI text detection with pattern diagnostics.

Public API:
    from ai_detect import classify_text, get_detector, MODELS
"""

from ._version import __version__
from .detector import classify_text, get_detector, is_model_cached, verdict
from .models import DEFAULT_MODEL, MODELS, REGISTRY
from .patterns import diagnose_sentence

__all__ = [
    "classify_text",
    "get_detector",
    "diagnose_sentence",
    "is_model_cached",
    "verdict",
    "MODELS",
    "REGISTRY",
    "DEFAULT_MODEL",
    "__version__",
]
