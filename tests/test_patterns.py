"""
Network-free tests for the pattern-diagnostics layer.

These don't download models — they exercise the pure-Python heuristics and text
metrics, so they run anywhere (CI included). Model-backed inference is smoke-
tested separately (see README "Run it").

    pytest            # or:  python tests/test_patterns.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ai_detect.patterns import (  # noqa: E402
    calculate_sdsl,
    count_pattern_totals,
    diagnose_sentence,
    sent_tokenize,
)
from ai_detect.detector import is_model_cached, verdict  # noqa: E402


def _patterns(text):
    return {f["pattern"] for f in diagnose_sentence(text)}


def test_missing_contraction_flagged():
    assert "missing_contraction" in _patterns("It is not the cheapest option.")


def test_contraction_passes_clean():
    assert "missing_contraction" not in _patterns("It isn't the cheapest option.")


def test_formal_verb_flagged():
    assert "formal_verb" in _patterns("The base provides excellent stability.")


def test_formal_transition_start_flagged():
    assert "formal_transition" in _patterns("Additionally, the app has improved.")


def test_ai_slop_flagged():
    assert "ai_slop" in _patterns("Let's delve into this robust, seamless solution.")


def test_for_who_frame_flagged():
    assert "ai_frame" in _patterns("For buyers who want value, this is ideal.")


def test_clean_sentence_has_no_findings():
    assert diagnose_sentence("Look, it isn't cheap, but I reckon it's worth it.") == []


def test_sent_tokenize_splits_on_boundaries():
    assert len(sent_tokenize("One thing. Two things! Three things?")) == 3


def test_sdsl_uniform_flagged_ai_like():
    uniform = ["word " * 8] * 5  # identical lengths -> cv ~ 0
    m = calculate_sdsl([s.strip() for s in uniform])
    assert m["cv"] < 0.3
    assert "uniform" in m["verdict"]


def test_verdict_thresholds():
    assert verdict(80) == "LIKELY AI"      # > 50
    assert verdict(50.1) == "LIKELY AI"
    assert verdict(45) == "MIXED"          # 40..50
    assert verdict(40) == "MIXED"
    assert verdict(39.9) == "LIKELY HUMAN"  # < 40


def test_is_model_cached_unknown_model_is_false():
    assert is_model_cached("no-such-model") is False


def test_pattern_totals_aggregate():
    data = [
        {"diagnostics": [{"pattern": "formal_verb"}, {"pattern": "ai_slop"}]},
        {"diagnostics": [{"pattern": "formal_verb"}]},
    ]
    totals = count_pattern_totals(data)
    assert totals == {"formal_verb": 2, "ai_slop": 1}


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
