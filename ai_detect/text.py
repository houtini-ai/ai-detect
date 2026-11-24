"""
Turning raw text into a structured document, and blocks into sentences.

A Document is an ordered list of Blocks (heading, paragraph, list item, table,
caption, quote, code). Plain text, Markdown and fetched web pages all become
the same structure, so scoring, the page-level tells and the web UI share one
model. Only prose blocks are split into sentences and sent to a detector;
headings, tables and code never are.
"""

import re
from dataclasses import dataclass, field

PROSE_KINDS = ("paragraph", "list_item", "quote", "caption")


@dataclass
class Block:
    kind: str                 # heading | paragraph | list_item | table | caption | quote | code
    text: str                 # visible text, markup removed
    level: int = 0            # heading level 1-6 (0 = inferred from layout)
    meta: dict = field(default_factory=dict)  # bold_lead, bold, ordered, list, inferred, rows...

    def as_dict(self):
        return {"kind": self.kind, "text": self.text, "level": self.level, "meta": self.meta}


@dataclass
class Document:
    blocks: list
    title: str = ""
    source: str = "text"      # text | file | url
    meta: dict = field(default_factory=dict)

    def as_dict(self):
        return {"title": self.title, "source": self.source, "meta": self.meta,
                "blocks": [b.as_dict() for b in self.blocks]}

    @property
    def text(self):
        return "\n\n".join(b.text for b in self.blocks if b.kind != "code")


# ---------------------------------------------------------------------------
# Inline markup
# ---------------------------------------------------------------------------

_BOLD_LEAD_RX = re.compile(
    r"^\s*(?:\*\*|__)([^*_\n]{1,60}?)(?::\s*(?:\*\*|__)|(?:\*\*|__)\s*[:–—-])\s*\S")
_BOLD_RX = re.compile(r"(\*\*|__)(?=\S)(.+?)(?<=\S)\1")
_INLINE_SUBS = [
    (re.compile(r"!\[([^\]]*)\]\([^)]*\)"), ""),                 # images
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),               # links
    (re.compile(r"\[([^\]]+)\]\[[^\]]*\]"), r"\1"),              # reference links
    (re.compile(r"<[^>\n]{1,200}>"), ""),                        # html tags, autolinks
    (_BOLD_RX, r"\2"),
    (re.compile(r"(?<![\w*])\*(?=\S)([^*\n]+?)(?<=\S)\*(?![\w*])"), r"\1"),
    (re.compile(r"(?<![\w_])_(?=\S)([^_\n]+?)(?<=\S)_(?![\w_])"), r"\1"),
    (re.compile(r"`([^`\n]+)`"), r"\1"),
    (re.compile(r"~~(.+?)~~"), r"\1"),
]


def strip_inline(text):
    """Remove Markdown/HTML inline markup, keeping the words a reader sees."""
    for rx, repl in _INLINE_SUBS:
        text = rx.sub(repl, text)
    return re.sub(r"[ \t]+", " ", text).strip()


def _inline_meta(raw):
    meta = {}
    lead = _BOLD_LEAD_RX.match(raw)
    if lead:
        meta["bold_lead"] = lead.group(1).strip()
    if _BOLD_RX.search(raw):
        meta["bold"] = True
    return meta


# ---------------------------------------------------------------------------
# Markdown / plain text -> blocks
# ---------------------------------------------------------------------------

_FENCE_RX = re.compile(r"^\s*(```|~~~)")
_HEADING_RX = re.compile(r"^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$")
_LIST_RX = re.compile(r"^(\s*)([-*+•]|\d{1,3}[.)])\s+(.*)$")
_QUOTE_RX = re.compile(r"^\s*>\s?(.*)$")
_TABLE_RX = re.compile(r"^\s*\|.*\|\s*$")
_RULE_RX = re.compile(r"^\s*([-*_=])(\s*\1){2,}\s*$")
_TERMINAL_RX = re.compile(r"[.!?:;,…]['\")\]’”]*$")
_FRONT_MATTER_RX = re.compile(r"\A---\s*\n.*?\n---\s*\n", re.DOTALL)
_DIVIDER_RX = re.compile(r":?-{2,}:?")


def parse_text(text, source="text", title=""):
    """Parse plain text or Markdown into a Document."""
    text = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    text = _FRONT_MATTER_RX.sub("", text)
    blocks, para, code = [], [], []
    in_code = False
    list_id = 0
    prev_was_list = False

    def flush():
        if not para:
            return
        single_line = len(para) == 1
        raw = " ".join(s.strip() for s in para)
        para.clear()
        plain = strip_inline(raw)
        if not plain:
            return
        meta = _inline_meta(raw)
        if (single_line and len(plain.split()) <= 10 and not _TERMINAL_RX.search(plain)
                and "bold_lead" not in meta):
            # One short line with no closing punctuation, standing alone, is a
            # heading in plain text. Inferred from layout, so level 0.
            blocks.append(Block("heading", plain, 0, {"inferred": True, **meta}))
        else:
            blocks.append(Block("paragraph", plain, 0, meta))

    for line in text.split("\n"):
        if _FENCE_RX.match(line):
            flush()
            if in_code:
                blocks.append(Block("code", "\n".join(code)))
                code = []
            in_code = not in_code
            continue
        if in_code:
            code.append(line)
            continue
        if not line.strip():
            flush()
            prev_was_list = False
            continue
        if _RULE_RX.match(line):
            if para and set(line.strip()) <= {"=", "-"}:  # setext heading underline
                plain = strip_inline(" ".join(para))
                para.clear()
                blocks.append(Block("heading", plain, 1 if "=" in line else 2))
            else:
                flush()
            continue
        m = _HEADING_RX.match(line)
        if m:
            flush()
            blocks.append(Block("heading", strip_inline(m.group(2)), len(m.group(1)),
                                _inline_meta(m.group(2))))
            prev_was_list = False
            continue
        if _TABLE_RX.match(line):
            flush()
            cells = [strip_inline(c) for c in line.strip().strip("|").split("|")]
            if all(_DIVIDER_RX.fullmatch(c.replace(" ", "")) for c in cells if c):
                continue
            if blocks and blocks[-1].kind == "table":
                blocks[-1].meta["rows"].append(cells)
                blocks[-1].text += "\n" + " | ".join(cells)
            else:
                blocks.append(Block("table", " | ".join(cells), 0, {"rows": [cells]}))
            continue
        m = _LIST_RX.match(line)
        if m:
            flush()
            if not prev_was_list:
                list_id += 1
            prev_was_list = True
            raw = m.group(3)
            meta = {"list": list_id, "ordered": m.group(2)[0].isdigit(),
                    "depth": len(m.group(1)) // 2, **_inline_meta(raw)}
            blocks.append(Block("list_item", strip_inline(raw), 0, meta))
            continue
        if line.lstrip().startswith(">"):
            flush()
            plain = strip_inline(_QUOTE_RX.match(line).group(1))
            if blocks and blocks[-1].kind == "quote" and plain:
                blocks[-1].text += " " + plain
            elif plain:
                blocks.append(Block("quote", plain))
            continue
        if prev_was_list and line[:1] in " \t" and blocks and blocks[-1].kind == "list_item":
            blocks[-1].text += " " + strip_inline(line)  # a wrapped list item
            continue
        prev_was_list = False
        para.append(line)
    flush()
    if in_code and code:
        blocks.append(Block("code", "\n".join(code)))
    if not title:
        title = next((b.text for b in blocks if b.kind == "heading"), "")
    return Document(blocks=blocks, title=title, source=source)


# ---------------------------------------------------------------------------
# Sentences
# ---------------------------------------------------------------------------

# Never the end of a sentence.
_ABBREV_INNER = {
    "e.g.", "i.e.", "vs.", "cf.", "mr.", "mrs.", "ms.", "dr.", "prof.", "st.", "mt.",
    "fig.", "no.", "nos.", "approx.", "ca.", "sr.", "jr.", "gen.", "col.", "lt.",
    "sgt.", "rev.", "hon.", "viz.", "incl.", "est.", "al.", "u.s.", "u.k.", "e.u.",
}
# The end of a sentence only when a capital follows.
_ABBREV_MAYBE = {"etc.", "inc.", "ltd.", "co.", "corp.", "a.m.", "p.m."}
_SPLIT_RX = re.compile(r"(?:(?<=[.!?])|(?<=[.!?][\"')\]’”]))\s+")
_INITIAL_RX = re.compile(r"(?:^|\s)[A-Z]\.$")


def split_sentences(text):
    """Split one block of prose into sentences.

    Splits on ., ! and ? followed by whitespace, then rejoins pieces that were
    cut inside an abbreviation ("e.g. on a Mac"), after a single initial
    ("J. Smith"), or before a lower-case continuation.
    """
    pieces = [p.strip() for p in _SPLIT_RX.split(text.strip()) if p.strip()]
    out = []
    for piece in pieces:
        if out and _should_join(out[-1], piece):
            out[-1] = out[-1] + " " + piece
        else:
            out.append(piece)
    return out


def _should_join(prev, nxt):
    first = nxt.lstrip("\"'([‘“")[:1]
    if not prev.endswith("."):
        # '"Really?" he asked.' : a lower-case word after a quoted ? or ! continues.
        return first.islower()
    last = prev.rsplit(None, 1)[-1].lower().lstrip("(\"'[")
    if last in _ABBREV_INNER or _INITIAL_RX.search(prev):
        return True
    if last in _ABBREV_MAYBE:
        return not first.isupper()
    return first.islower()


def sent_tokenize(text):
    """Split text into sentences, one block at a time, so a heading or a list
    item never merges into the paragraph after it. Headings come back as their
    own items; tables and code are left out."""
    out = []
    for block in parse_text(text).blocks:
        if block.kind in PROSE_KINDS:
            out.extend(split_sentences(block.text))
        elif block.kind == "heading":
            out.append(block.text)
    return out
