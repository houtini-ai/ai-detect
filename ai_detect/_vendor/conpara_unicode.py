# Vendored from https://github.com/SES-Lab-OTH/deberta-conpara
# (src/unicode_preprocessing_v2.py, read 24 Nov 2026), unmodified below this header.
# MIT License, Copyright (c) 2026 Mohamed Mady. Full text: ai_detect/_vendor/LICENSE-conpara.
# The DeBERTa-ConPara detector is only robust when its input goes through exactly this
# normaliser at inference, so it is carried as-is rather than re-implemented.
#!/usr/bin/env python3
"""
Unicode Preprocessing v2 — Optimized for RAID Adversarial Robustness
=====================================================================
Drop-in replacement for `unicode_normalize()` in test_preprocessing_effect.py.

Three-layer defence:
  Layer 1 — Explicit homoglyph confusables  (Cyrillic/Greek/Fullwidth → Latin)
  Layer 2 — NFKD decomposition + combining-mark strip  (accented Latin → ASCII)
  Layer 3 — Typographic normalization  (smart quotes, dashes, symbols → ASCII)
  Layer 4 — Strip invisible / format characters  (ZWSP, Cf category)

Author : Mohamed Mady
Date   : 2026-03-10
"""

import unicodedata
import re

# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 1 — EXPLICIT HOMOGLYPH CONFUSABLES
# ═══════════════════════════════════════════════════════════════════════════════
# Only characters that are visually similar to Latin characters but come from
# other scripts.  NFKD cannot fix these because they are canonically distinct.
#
# CORRECTIONS from v1:
#   ı (U+0131) → 'i'  (was 'd' — Turkish dotless i looks like i, not d)
#   н (U+043D) → 'h'  (was 'e' — Cyrillic EN looks like lowercase h)
#   л (U+043B) → 'n'  (was 'e' — Cyrillic EL looks like inverted-V / n in many fonts)
#   м (U+043C) → 'm'  (was 'e' — Cyrillic EM is visually m)
#   Л (U+041B) → 'L'  (was 'e' — Cyrillic capital EL)
#   Ζ (U+0396) → 'Z'  (was 'z' — it's uppercase, map to uppercase)
#   ς (U+03C2) → 's'  (was 'f' — final sigma looks like s, not f)
#   ф (U+0444) → 'f'  (was 'e' — Cyrillic EF looks like f in many fonts)

CONFUSABLES = {
    # ── Cyrillic → Latin (lowercase) ──────────────────────────────────────
    '\u0430': 'a',   # а
    '\u0435': 'e',   # е
    '\u043e': 'o',   # о
    '\u0440': 'p',   # р (VISUAL: looks like Latin p)
    '\u0423': 'Y',   # У (VISUAL: Latin Y)
    '\u0455': 's',   # ѕ (VISUAL: Latin s)
    '\u0458': 'j',   # ј (VISUAL: Latin j)
    '\u04bb': 'h',   # һ (VISUAL: Latin h)
    '\u0441': 'c',   # с
    '\u0445': 'x',   # х
    '\u0456': 'i',   # і
    '\u0443': 'y',   # у
    '\u0451': 'e',   # ё
    '\u0438': 'i',   # и  (NEW — count=2,119)
    '\u043d': 'h',   # н  (FIXED: was 'e' → 'h')
    '\u0432': 'v',   # в  (NEW — count=1,383)
    '\u0442': 't',   # т  (NEW — count=1,305)
    '\u043b': 'n',   # л  (FIXED: was 'e' → 'n')
    '\u043a': 'k',   # к  (NEW — count=794)
    '\u043c': 'm',   # м  (FIXED: was 'e' → 'm')
    '\u0447': 'c',   # ч  (NEW — count=603)
    '\u0434': 'd',   # д  (NEW — count=585)
    '\u043f': 'p',   # п  (NEW — count=363)
    '\u044c': "'",   # ь  soft sign  (NEW — count=342)
    '\u0433': 'g',   # г  (NEW — count=320)
    '\u044b': 'y',   # ы  (NEW — count=310)
    '\u0439': 'i',   # й  short I  (NEW — count=444)
    '\u044f': 'ya',  # я  (NEW — count=439)
    '\u0431': 'b',   # б  (NEW — count=258)
    '\u0437': 'z',   # з  (NEW — count=249)
    '\u0436': 'zh',  # ж  (NEW — count=111)
    '\u0446': 'ts',  # ц  (NEW — count=120)
    '\u0448': 'sh',  # ш  (NEW — count=133)
    '\u044e': 'yu',  # ю  (NEW — count=132)
    '\u0444': 'f',   # ф  (FIXED: was 'e' → 'f', count=52)
    '\u045b': 't',   # ћ  tshe  (NEW — count=68)

    # ── Cyrillic → Latin (uppercase) ──────────────────────────────────────
    '\u0406': 'I',   # І
    '\u0410': 'A',   # А
    '\u0412': 'B',   # В
    '\u0415': 'E',   # Е
    '\u041a': 'K',   # К
    '\u041c': 'M',   # М
    '\u041d': 'H',   # Н
    '\u041e': 'O',   # О
    '\u0420': 'P',   # Р
    '\u0421': 'C',   # С
    '\u0422': 'T',   # Т
    '\u0425': 'X',   # Х
    '\u0418': 'I',   # И  (NEW — count=104)
    '\u0411': 'B',   # Б  (NEW — count=159)
    '\u041b': 'L',   # Л  (FIXED: was 'e' → 'L', count=128)
    '\u041f': 'P',   # П  (NEW — count=119)
    '\u0414': 'D',   # Д  (NEW — count=88)
    '\u0428': 'Sh',  # Ш  (NEW — count=64)

    # ── Greek → Latin (lowercase) ─────────────────────────────────────────
    '\u03b1': 'a',   # α
    '\u03b5': 'e',   # ε
    '\u03b7': 'n',   # η
    '\u03b9': 'i',   # ι
    '\u03ba': 'k',   # κ
    '\u03bd': 'v',   # ν
    '\u03bf': 'o',   # ο
    '\u03c1': 'p',   # ρ  (visually similar to p)
    '\u03c5': 'u',   # υ
    '\u03c7': 'x',   # χ
    '\u03c4': 't',   # τ  (NEW — count=1,668)
    '\u03bc': 'm',   # μ  (NEW — count=1,401)
    '\u03c3': 's',   # σ  (NEW — count=971)
    '\u03c0': 'p',   # π  (NEW — count=962)
    '\u03bb': 'l',   # λ  (NEW — count=857)
    '\u03c2': 's',   # ς  final sigma (FIXED: was 'f' → 's', count=784)
    '\u03c9': 'o',   # ω  (NEW — count=523)
    '\u03b4': 'd',   # δ  (NEW — count=487)
    '\u03b3': 'g',   # γ  (NEW — count=467)
    '\u03b8': 'th',  # θ  (NEW — count=464)
    '\u03b2': 'b',   # β  (NEW — count=463)
    '\u03b6': 'z',   # ζ  (NEW — count=124)
    '\u03c6': 'ph',  # φ  (NEW — count=272)
    '\u03c8': 'ps',  # ψ  (NEW — count=108)
    '\u03be': 'x',   # ξ  (NEW — count=86)
    '\u03d5': 'ph',  # ϕ  phi symbol (NEW — count=52)
    # Greek with tonos (accented)
    '\u03af': 'i',   # ί  (NEW — count=514)
    '\u03ac': 'a',   # ά  (NEW — count=435)
    '\u03cc': 'o',   # ό  (NEW — count=364)
    '\u03ad': 'e',   # έ  (NEW — count=339)
    '\u03ae': 'e',   # ή  (NEW — count=269)
    '\u03cd': 'u',   # ύ  (NEW — count=193)
    '\u03ce': 'o',   # ώ  (NEW — count=155)

    # ── Greek → Latin (uppercase) ─────────────────────────────────────────
    '\u0391': 'A',   # Α
    '\u0392': 'B',   # Β
    '\u0395': 'E',   # Ε
    '\u0397': 'H',   # Η
    '\u0399': 'I',   # Ι
    '\u039a': 'K',   # Κ
    '\u039c': 'M',   # Μ
    '\u039d': 'N',   # Ν
    '\u039f': 'O',   # Ο
    '\u03a1': 'P',   # Ρ
    '\u03a4': 'T',   # Τ
    '\u03a7': 'X',   # Χ
    '\u0396': 'Z',   # Ζ  (FIXED: was lowercase 'z' → 'Z', count=35,053)
    '\u0393': 'G',   # Γ  (NEW — count=114)
    '\u0394': 'D',   # Δ  (NEW — count=160)
    '\u039b': 'L',   # Λ  (NEW — count=62)
    '\u03a0': 'P',   # Π  (NEW — count=65)
    '\u03a3': 'S',   # Σ  (NEW — count=176)
    '\u03a6': 'Ph',  # Φ  (NEW — count=66)
    '\u03a9': 'O',   # Ω  (NEW — count=202)

    # ── Fullwidth Latin → ASCII ───────────────────────────────────────────
    '\uff41': 'a', '\uff42': 'b', '\uff43': 'c', '\uff44': 'd', '\uff45': 'e',
    '\uff46': 'f', '\uff47': 'g', '\uff48': 'h', '\uff49': 'i', '\uff4a': 'j',
    '\uff4b': 'k', '\uff4c': 'l', '\uff4d': 'm', '\uff4e': 'n', '\uff4f': 'o',
    '\uff50': 'p', '\uff51': 'q', '\uff52': 'r', '\uff53': 's', '\uff54': 't',
    '\uff55': 'u', '\uff56': 'v', '\uff57': 'w', '\uff58': 'x', '\uff59': 'y',
    '\uff5a': 'z',
    '\uff21': 'A', '\uff22': 'B', '\uff23': 'C', '\uff24': 'D', '\uff25': 'E',
    '\uff26': 'F', '\uff27': 'G', '\uff28': 'H', '\uff29': 'I', '\uff2a': 'J',
    '\uff2b': 'K', '\uff2c': 'L', '\uff2d': 'M', '\uff2e': 'N', '\uff2f': 'O',
    '\uff30': 'P', '\uff31': 'Q', '\uff32': 'R', '\uff33': 'S', '\uff34': 'T',
    '\uff35': 'U', '\uff36': 'V', '\uff37': 'W', '\uff38': 'X', '\uff39': 'Y',
    '\uff3a': 'Z',
    # Fullwidth digits
    '\uff10': '0', '\uff11': '1', '\uff12': '2', '\uff13': '3', '\uff14': '4',
    '\uff15': '5', '\uff16': '6', '\uff17': '7', '\uff18': '8', '\uff19': '9',
    # Fullwidth punctuation
    '\uff01': '!', '\uff0c': ',', '\uff0e': '.', '\uff1a': ':', '\uff1b': ';',
    '\uff1f': '?', '\uff08': '(', '\uff09': ')',

    # ── Latin Extended look-alikes ────────────────────────────────────────
    '\u0131': 'i',   # ı  dotless i (FIXED: was 'd' → 'i', count=5,734)
    '\u0130': 'I',   # İ  dotted I  (NEW — count=249)
    '\u0142': 'l',   # ł  (NEW — count=307)
    '\u00f0': 'd',   # ð  eth  (count=174 — better mapped to 'd' than 'e')
    '\u00fe': 'th',  # þ  thorn  (count=58)
    '\u00de': 'Th',  # Þ  Thorn  (count=95)
    '\u00df': 'ss',  # ß  sharp s  (count=368)
    '\u00e6': 'ae',  # æ  (count=347)
    '\u00c6': 'Ae',  # Æ  (count=215)
    '\u0153': 'oe',  # œ  (count=101)
    '\u0152': 'Oe',  # Œ
    '\u0259': 'e',   # ə  schwa  (count=285)
    '\u026a': 'i',   # ɪ  small capital I (count=153)
    '\u025b': 'e',   # ɛ  open E (count=145)
    '\u0254': 'o',   # ɔ  open O (count=89)
    '\u0251': 'a',   # ɑ  Latin alpha (count=87)
    '\u0250': 'a',   # ɐ  turned a (count=64)
    '\u028a': 'u',   # ʊ  upsilon (count=57)
    '\u0283': 'sh',  # ʃ  esh (count=61)
    '\u0292': 'zh',  # ʒ  ezh (count=58)
    '\u0281': 'r',   # ʁ  inverted R (count=63)
    '\u2113': 'l',   # ℓ  script small L (count=76)

    # ── Letterlike symbols ────────────────────────────────────────────────
    '\u2103': 'C',   # ℃  degree Celsius
    '\u2109': 'F',   # ℉  degree Fahrenheit
    '\u212b': 'A',   # Å  angstrom
}


# ═══════════════════════════════════════════════════════════════════════════════
# LAYER 3 — TYPOGRAPHIC NORMALIZATION
# ═══════════════════════════════════════════════════════════════════════════════
# These are NOT homoglyphs — they are normal typographic characters.
# But they affect tokenization (DeBERTa treats U+2019 ≠ U+0027), so
# normalizing them removes an uncontrolled variable.

TYPOGRAPHIC = {
    # Quotes
    '\u2018': "'",   # '  left single
    '\u2019': "'",   # '  right single  (count=78,314 — #1 by frequency!)
    '\u201a': "'",   # ‚  single low-9
    '\u201b': "'",   # ‛  single high-reversed-9
    '\u201c': '"',   # "  left double
    '\u201d': '"',   # "  right double
    '\u201e': '"',   # „  double low-9
    '\u201f': '"',   # ‟  double high-reversed-9
    '\u00ab': '"',   # «  left guillemet
    '\u00bb': '"',   # »  right guillemet
    '\u2039': "'",   # ‹  single left guillemet
    '\u203a': "'",   # ›  single right guillemet
    '\u0060': "'",   # `  grave accent (sometimes used as quote)
    '\u00b4': "'",   # ´  acute accent
    # Dashes
    '\u2013': '-',   # –  en dash   (count=55,032)
    '\u2014': '--',  # —  em dash   (count=24,725)
    '\u2015': '--',  # ―  horizontal bar
    '\u2012': '-',   # ‒  figure dash
    '\u2212': '-',   # −  minus sign  (count=818)
    '\uff0d': '-',   # ﹣ fullwidth hyphen-minus
    # Ellipsis
    '\u2026': '...',  # …  (count=25,340)
    # Spaces
    '\u00a0': ' ',   # no-break space  (count=5,407)
    '\u2002': ' ',   # en space
    '\u2003': ' ',   # em space
    '\u2009': ' ',   # thin space
    '\u200a': ' ',   # hair space
    '\u202f': ' ',   # narrow no-break space
    '\u205f': ' ',   # medium mathematical space
    # Bullets / dots
    '\u2022': '*',   # •  bullet  (count=6,029)
    '\u00b7': '.',   # ·  middle dot  (count=1,000)
    # Math / symbols
    '\u00d7': 'x',   # ×  multiplication  (count=1,221)
    '\u00f7': '/',   # ÷  division
    '\u2260': '!=',  # ≠
    '\u2264': '<=',  # ≤
    '\u2265': '>=',  # ≥
    '\u2248': '~',   # ≈
    # Fractions → text (avoids unknown tokens)
    '\u00bd': '1/2',  # ½  (count=9,508)
    '\u00bc': '1/4',  # ¼  (count=5,211)
    '\u00be': '3/4',  # ¾  (count=2,200)
    '\u2153': '1/3',  # ⅓
    '\u2154': '2/3',  # ⅔
    # Misc
    '\u00b0': ' degrees',  # °  degree sign  (count=35,269)
    '\ufffd': '',     # � replacement character — pure noise, strip it
}


# ═══════════════════════════════════════════════════════════════════════════════
# COMBINED NORMALIZATION FUNCTION
# ═══════════════════════════════════════════════════════════════════════════════
# Build a single lookup table for maximum speed
_COMBINED_MAP = {}
_COMBINED_MAP.update(CONFUSABLES)
_COMBINED_MAP.update(TYPOGRAPHIC)

# Pre-build translation table for single-char mappings (faster than dict lookup)
_SINGLE_CHAR = {ord(k): v for k, v in _COMBINED_MAP.items() if len(v) <= 1}
_MULTI_CHAR  = {k: v for k, v in _COMBINED_MAP.items() if len(v) > 1}


def unicode_normalize(text: str) -> str:
    """
    Four-layer Unicode normalization for adversarial robustness.

    Layer 1: Explicit homoglyph substitution (Cyrillic/Greek/Fullwidth → Latin)
    Layer 2: NFKD decomposition + combining-mark strip  (é → e, ü → u, etc.)
    Layer 3: Typographic normalization (smart quotes, dashes, fractions → ASCII)
    Layer 4: Strip invisible format characters (ZWSP, ZWNJ, BOM, etc.)

    This function is idempotent: applying it twice gives the same result.
    """
    if not text:
        return text

    # ── Layer 1 + 3: Apply all explicit mappings ──────────────────────────
    # Single-char mappings via str.translate (C-speed)
    text = text.translate(_SINGLE_CHAR)
    # Multi-char mappings (e.g. ß → ss, — → --, θ → th)
    for src, dst in _MULTI_CHAR.items():
        if src in text:
            text = text.replace(src, dst)

    # ── Layer 2: NFKD decomposition + strip combining marks ──────────────
    # This handles ALL accented Latin characters automatically:
    #   é → e + ◌́  → strip mark → e
    #   ü → u + ◌̈  → strip mark → u
    #   ñ → n + ◌̃  → strip mark → n
    # Also normalizes compatibility forms (e.g. ﬁ → fi, ² → 2)
    text = unicodedata.normalize('NFKD', text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Mn')
    # Re-compose any remaining valid sequences
    text = unicodedata.normalize('NFC', text)

    # ── Layer 4: Strip invisible format characters (Cf category) ──────────
    # Catches: ZWSP (U+200B), ZWNJ (U+200C), ZWJ (U+200D), BOM (U+FEFF),
    #          LRM (U+200E), RLM (U+200F), soft hyphen (U+00AD), etc.
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')

    # ── Cleanup: collapse multiple spaces ─────────────────────────────────
    text = re.sub(r'  +', ' ', text)

    return text


# ═══════════════════════════════════════════════════════════════════════════════
# LEGACY WRAPPER  (drop-in for old code)
# ═══════════════════════════════════════════════════════════════════════════════
def unicode_normalize_v1(text: str) -> str:
    """Original v1 normalization — kept for A/B comparison."""
    CONFUSABLES_V1 = {
        '\u0430': 'a', '\u0435': 'e', '\u043e': 'o', '\u0440': 'p',
        '\u0441': 'c', '\u0445': 'x', '\u0456': 'i', '\u0443': 'y',
        '\u0451': 'e', '\u0406': 'I', '\u0410': 'A', '\u0412': 'B',
        '\u0415': 'E', '\u041a': 'K', '\u041c': 'M', '\u041d': 'H',
        '\u041e': 'O', '\u0420': 'P', '\u0421': 'C', '\u0422': 'T',
        '\u0425': 'X', '\u03b1': 'a', '\u03b5': 'e', '\u03b7': 'n',
        '\u03b9': 'i', '\u03ba': 'k', '\u03bd': 'v', '\u03bf': 'o',
        '\u03c1': 'p', '\u03c5': 'u', '\u03c7': 'x', '\u0391': 'A',
        '\u0392': 'B', '\u0395': 'E', '\u0397': 'H', '\u0399': 'I',
        '\u039a': 'K', '\u039c': 'M', '\u039d': 'N', '\u039f': 'O',
        '\u03a1': 'P', '\u03a4': 'T', '\u03a7': 'X',
        '\uff41': 'a', '\uff45': 'e', '\uff49': 'i', '\uff4f': 'o', '\uff55': 'u',
        '\uff21': 'A', '\uff25': 'E', '\uff29': 'I', '\uff2f': 'O', '\uff35': 'U',
    }
    text = ''.join(CONFUSABLES_V1.get(c, c) for c in text)
    text = ''.join(c for c in text if unicodedata.category(c) != 'Cf')
    return text


# ═══════════════════════════════════════════════════════════════════════════════
# STATS / TESTING
# ═══════════════════════════════════════════════════════════════════════════════
def count_surviving_nonascii(text: str) -> dict:
    """Count non-ASCII characters remaining after normalization."""
    counts = {}
    for c in text:
        if ord(c) > 127:
            counts[c] = counts.get(c, 0) + 1
    return counts


def get_normalization_stats(raw_text: str) -> dict:
    """Compare v1 vs v2 normalization on a single text."""
    v1 = unicode_normalize_v1(raw_text)
    v2 = unicode_normalize(raw_text)

    raw_non = sum(1 for c in raw_text if ord(c) > 127)
    v1_non  = sum(1 for c in v1 if ord(c) > 127)
    v2_non  = sum(1 for c in v2 if ord(c) > 127)

    return {
        'raw_nonascii':  raw_non,
        'v1_nonascii':   v1_non,
        'v2_nonascii':   v2_non,
        'v1_fixed':      raw_non - v1_non,
        'v2_fixed':      raw_non - v2_non,
        'v2_improvement': (v1_non - v2_non),
    }


if __name__ == '__main__':
    # Quick self-test
    tests = [
        ("Hеllo wоrld",        "Hello world",    "Basic Cyrillic homoglyphs"),
        ("It\u2019s a tеst",   "It's a test",    "Smart quote + Cyrillic"),
        ("café résumé naïve",  "cafe resume naive", "Accented Latin (NFKD)"),
        ("½ cup of ﬂour",      "1/2 cup of flour",  "Fraction + ligature"),
        ("zero\u200Bwidth",    "zerowidth",       "Zero-width space"),
        ("Ζero day",           "Zero day",        "Greek Zeta (U+0396)"),
        ("türkçe ışık",        "turkce isik",     "Turkish chars"),
        ("naïve\u00A0café",    "naive cafe",      "NBSP + accents"),
        ("Straße München",     "Strasse Munchen", "German special chars"),
    ]

    print("=" * 70)
    print("  Unicode Preprocessing v2 — Self-Test")
    print("=" * 70)
    all_pass = True
    for raw, expected, desc in tests:
        result = unicode_normalize(raw)
        ok = result == expected
        status = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{status}] {desc}")
        if not ok:
            print(f"         Input   : {repr(raw)}")
            print(f"         Expected: {repr(expected)}")
            print(f"         Got     : {repr(result)}")

    print(f"\n  Table size: {len(CONFUSABLES)} homoglyphs + {len(TYPOGRAPHIC)} typographic")
    print(f"  Total mappings: {len(_COMBINED_MAP)}")
    print(f"  Result: {'ALL PASSED' if all_pass else 'SOME FAILED'}\n")
