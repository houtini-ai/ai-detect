from ai_detect.normalize import strip_invisible, fold_lookalikes, fold_typography, NORMALIZERS, normalizer, collapse_whitespace
import unicodedata

def test_strip_invisible_chars():
    text = "a\u200bb\u00ad"
    assert strip_invisible(text) == "ab"

def test_fold_lookalikes_mixed():
    # Cyrillic 'a' in pаss (p is latin, а is cyrillic)
    text = "p\u0430ss"
    assert fold_lookalikes(text) == "pass"

def test_fold_lookalikes_pure_cyrillic():
    # A fully Cyrillic sentence should remain unchanged
    text = "\u0418\u043c\u044f \u0418\u0432\u0430\u043d"
    assert fold_lookalikes(text) == text

def test_fold_typography():
    text = "\u201cCurly\u201d \u2014 Em"
    # Curly quotes become ASCII, em dash stays
    assert fold_typography(text) == "\"Curly\" — Em"

def test_nfkc_collapse_whitespace():
    text = "a   b\u2002\u2009c"
    result = NORMALIZERS["nfkc"](text)
    assert "   " not in result
    assert "a b c" in result

def test_normalizer_unknown():
    try:
        normalizer("nope")
        assert False
    except ValueError:
        pass

def test_normalizer_none():
    assert NORMALIZERS["none"]("test") == "test"
