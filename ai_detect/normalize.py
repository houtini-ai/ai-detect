"""
Input normalisers, applied to text just before it reaches a model.

Several detectors were trained (or are documented to be scored) on text that
has had invisible characters and look-alike letters cleaned up first. Each
ModelSpec names the normaliser its model card asks for. These are independent
implementations written from the cards' descriptions, not copies of upstream
code. They change what the MODEL sees; reports always quote the original text.
"""

import re
import unicodedata

# Cyrillic and Greek letters that render like a Latin letter in most fonts.
_LOOKALIKES = str.maketrans({
    "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x",
    "і": "i", "ј": "j", "ѕ": "s", "һ": "h", "ԁ": "d", "ԛ": "q", "ԝ": "w", "ӏ": "l",
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M", "Н": "H", "О": "O",
    "Р": "P", "С": "C", "Т": "T", "Х": "X", "І": "I", "Ј": "J", "Ѕ": "S",
    "Ү": "Y", "Ԁ": "D", "Ԛ": "Q", "Ԝ": "W",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H", "Ι": "I", "Κ": "K",
    "Μ": "M", "Ν": "N", "Ο": "O", "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X",
    "ο": "o", "ν": "v", "ι": "i", "κ": "k", "ρ": "p", "τ": "t", "υ": "u",
    "χ": "x", "α": "a",
})
_LOOKALIKE_RX = re.compile("[" + "".join(chr(c) for c in _LOOKALIKES) + "]")
_GREEK_CYRILLIC_RX = re.compile("[Ͱ-ϿЀ-ԯ]")
_LATIN_RX = re.compile("[A-Za-z]")
_WORD_RX = re.compile(r"[^\W\d_]+")
_SPACE_RX = re.compile(r"\s+")

_TYPOGRAPHY = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "…": "...", " ": " ", " ": " ",
})


def strip_invisible(text):
    """Drop format characters (zero-width space/joiner, BOM, soft hyphen...) and
    variation selectors. They carry no meaning and are a known evasion trick."""
    return "".join(
        c for c in text
        if unicodedata.category(c) != "Cf" and not "︀" <= c <= "️"
    )


def fold_lookalikes(text):
    """Map Cyrillic/Greek look-alike letters to Latin, in mostly-Latin text only.

    Genuinely Greek or Cyrillic text is left alone: a word is only rewritten if
    doing so leaves it with no Greek/Cyrillic letters at all, and nothing is
    rewritten unless Latin letters outnumber the other non-look-alike letters.
    """
    lookalikes = _LOOKALIKE_RX.findall(text)
    if not lookalikes:
        return text
    other_foreign = len(_GREEK_CYRILLIC_RX.findall(text)) - len(lookalikes)
    if len(_LATIN_RX.findall(text)) <= other_foreign:
        return text

    def fix(match):
        word = match.group(0)
        mapped = word.translate(_LOOKALIKES)
        return word if _GREEK_CYRILLIC_RX.search(mapped) else mapped

    return _WORD_RX.sub(fix, text)


def fold_typography(text):
    """Curly quotes, primes, the ellipsis character and no-break spaces to ASCII.
    Dashes are left alone."""
    return text.translate(_TYPOGRAPHY)


def collapse_whitespace(text):
    return _SPACE_RX.sub(" ", text).strip()


def _none(text):
    return text


def _invisible_lookalike(text):
    return fold_lookalikes(strip_invisible(str(text)))


def _nfkc(text):
    return collapse_whitespace(strip_invisible(unicodedata.normalize("NFKC", str(text))))


NORMALIZERS = {
    "none": _none,
    # GPTTrace cards: "undoes zero-width characters and Cyrillic/Greek homoglyphs".
    "invisible+lookalike": _invisible_lookalike,
    # Tabularis card: NFKC, strip zero-width invisibles, collapse whitespace.
    "nfkc": _nfkc,
}


def normalizer(name):
    try:
        return NORMALIZERS[name]
    except KeyError:
        raise ValueError(f"Unknown normalizer '{name}'") from None
