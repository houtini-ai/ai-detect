"""Page-level "structure and style" tells: prose habits and page shape.

These look at a whole parsed Document, not one sentence: how sections open and
close, how often lists come in threes, whether every heading is a question,
whether paragraphs are all the same length. Each tell is reported with where
it is, an example quoted from the page, and a plain suggestion.

They are a separate signal. They never feed the model score, and none of them
proves anything on its own: people write em dashes and three-item lists too.
What they measure is how much a page leans on the habits that machine-written
copy leans on. Read the count and the density, not any single hit.

Each tell is a dict:
    id, family ("prose" | "structure"), label, severity ("low" | "medium" | "high"),
    block (index into document.blocks, or None for a whole-page tell),
    blocks (every block involved, for highlighting), example, suggestion, detail
"""

import re
import statistics

from .patterns import AI_SLOP, _inflected
from .text import PROSE_KINDS, split_sentences

MAX_PER_TELL = 12  # instances listed per tell id; the rest are counted in the summary

_WORD = r"[A-Za-z][\w'’-]*"
_ITEM = rf"(?:{_WORD}(?:\s+{_WORD})?)"
# "fast, simple, and secure": three short items, then the sentence moves on.
_TRIAD_RX = re.compile(
    rf"\b({_ITEM}),\s+({_ITEM}),?\s+(?:and|or)\s+({_ITEM})"
    r"(?=[.,;:!?)]|\s+(?:of|for|in|to|as|that|with|across|into|while|when|your|our|their|you)\b|$)")
_NOT_BUT_RX = re.compile(
    r"\bnot\s+(?:just|merely|simply|only)\s+[^.;:!?]{2,80}?[,;]?\s+but(?:\s+also)?\b"
    r"|\b(?:is|are|was|isn['’]t|aren['’]t|wasn['’]t)\s*(?:not\s+)?(?:just\s+|merely\s+|only\s+)?"
    r"(?:about\s+)?[^.;:!?,]{2,50}[,;—–-]+\s*(?:it|they|this|that)(?:['’]s|\s+is|\s+are)\s+",
    re.IGNORECASE)
_NOT_PAIR_RX = re.compile(r"^(?:It|This|That|They)\s*(?:['’]s|is|are)\s+not\b|^(?:It|This|That)\s+isn['’]t\b",
                          re.IGNORECASE)
_ITS_RX = re.compile(r"^(?:It|This|That|They)(?:['’]s|\s+is|['’]re|\s+are)\s+", re.IGNORECASE)
_CLOSER_RX = re.compile(
    r"^(?:In short|In summary|In conclusion|In essence|In the end|Ultimately|Overall|All in all|"
    r"Simply put|Put simply|The bottom line|Bottom line|At the end of the day|To sum up|"
    r"To summari[sz]e|To wrap up|The takeaway|The result\?|The key takeaway)\b", re.IGNORECASE)
_OPENER_RX = re.compile(
    r"^(?:In today['’]s\b|In the (?:world|realm|age|era) of\b|In an? (?:era|age|world)\b|"
    r"When it comes to\b|In recent years\b|As (?:we|businesses|technology)\b.{0,40}\bcontinue|"
    r"Have you ever wondered\b|If you['’]ve ever wondered\b|It['’]s no secret that\b|"
    r"In this (?:article|guide|post)\b|Let['’]s (?:dive|explore|take a look|unpack|break)\b)",
    re.IGNORECASE)
_DEFINE_RX = re.compile(
    rf"^((?:{_WORD}\s+){{0,4}}{_WORD})\s+(?:is|are|refers to|can be defined as)\s+"
    r"(?:a|an|the|one of the)\b", re.IGNORECASE)
_TAIL_RX = re.compile(
    r",\s+(?:ensuring|making|allowing|enabling|providing|highlighting|underscoring|emphasi[sz]ing|"
    r"reflecting|showcasing|contributing|fostering|creating|offering|helping|leading|resulting|"
    r"paving|driving|empowering|solidifying|cementing)\b[^.!?]{8,}[.!]?$", re.IGNORECASE)
_HEDGE_RX = re.compile(
    r"\b(?:may|might|can|could|will) (?:vary|differ|depend)\b|\bdepending on (?:your|the|individual|specific)\b|"
    r"\bit(?:['’]s| is) (?:important|worth|essential|crucial) to (?:note|remember|consider|understand)\b|"
    r"\bgenerally speaking\b|\bin (?:many|most|some) cases\b|\bto some extent\b", re.IGNORECASE)
_SIGNPOST_RX = re.compile(
    r"\bWhether you['’]re\b|\bHere['’]s (?:the thing|what you need to know|why|how)\b|"
    r"\bLet['’]s (?:dive|delve|explore|unpack|break (?:it|this) down)\b|\bThe truth is\b|"
    r"\bThe reality is\b|\bLook no further\b|\bhas you covered\b|\bWithout further ado\b|"
    r"\bthe (?:best|good) news is\b|\bYou might be (?:wondering|surprised)\b", re.IGNORECASE)
_STOCK = AI_SLOP + [
    "testament", "pivotal", "meticulous", "intricate", "paramount", "bustling", "beacon",
    "cornerstone", "embark", "resonate", "nuanced", "vibrant", "ever-evolving", "fast-paced",
    "comprehensive", "invaluable", "indispensable", "transformative", "unparalleled",
    "world-class", "next-level", "supercharge", "harness", "bespoke", "curated",
]
_STOCK_RX = re.compile(r"\b(?:" + "|".join(sorted({_inflected(w) for w in _STOCK}, key=len, reverse=True))
                       + r")\b", re.IGNORECASE)
_EMOJI_RX = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF⭐⬆✅❌✨⭕]")
_FAQ_RX = re.compile(r"\b(?:faqs?|frequently asked|common questions|questions? (?:and|&) answers?)\b",
                     re.IGNORECASE)
_CONCLUSION_RX = re.compile(r"^(?:conclusion|final thoughts|in conclusion|wrapping up|the bottom line|"
                            r"key takeaways?|summary|closing thoughts)\s*:?$", re.IGNORECASE)
_SMALL_WORDS = {"a", "an", "the", "and", "or", "but", "nor", "for", "of", "in", "on", "at", "to",
                "by", "with", "from", "as", "vs", "via", "is", "it"}
_STOPWORDS = _SMALL_WORDS | {
    "this", "that", "these", "those", "are", "was", "were", "be", "been", "has", "have", "had",
    "you", "your", "we", "our", "they", "their", "its", "can", "will", "do", "does", "not",
    "what", "how", "why", "when", "which", "who", "much", "more", "so", "if", "then", "than",
}


def _snip(text, start=0, end=None, width=140):
    """A short quotation around a match."""
    end = len(text) if end is None else end
    if len(text) <= width:
        return text
    left = max(0, start - (width - (end - start)) // 2)
    right = min(len(text), left + width)
    return ("…" if left else "") + text[left:right].strip() + ("…" if right < len(text) else "")


def _cv(values):
    mean = statistics.fmean(values)
    return statistics.pstdev(values) / mean if mean else 0.0


def _content_words(text):
    return {w for w in re.findall(r"[a-z0-9']+", text.lower()) if w not in _STOPWORDS and len(w) > 2}


def _is_title_case(text):
    words = [w for w in re.findall(r"[A-Za-z][A-Za-z'’-]*", text)]
    if len(words) < 3:
        return False
    major = [w for i, w in enumerate(words) if i == 0 or w.lower() not in _SMALL_WORDS]
    capped = sum(w[0].isupper() for w in major)
    return len(major) >= 3 and capped == len(major)


class _Collector:
    def __init__(self):
        self.tells = []
        self.counts = {}

    def add(self, id, family, label, severity, suggestion, example="", block=None,
            blocks=None, detail=""):
        self.counts[id] = self.counts.get(id, 0) + 1
        if self.counts[id] > MAX_PER_TELL:
            return
        involved = blocks if blocks is not None else ([block] if block is not None else [])
        self.tells.append({
            "id": id, "family": family, "label": label, "severity": severity,
            "block": block, "blocks": involved, "example": example,
            "suggestion": suggestion, "detail": detail,
        })


def find_tells(document):
    """Return ``{"tells": [...], "summary": {...}}`` for a parsed Document."""
    c = _Collector()
    blocks = document.blocks
    prose = [(i, b) for i, b in enumerate(blocks) if b.kind in PROSE_KINDS]
    paragraphs = [(i, b) for i, b in prose if b.kind == "paragraph"]
    headings = [(i, b) for i, b in enumerate(blocks) if b.kind == "heading"]
    items = [(i, b) for i, b in enumerate(blocks) if b.kind == "list_item"]
    words_total = sum(len(b.text.split()) for _, b in prose) or 1

    _prose_tells(c, blocks, prose, words_total)
    _section_tells(c, blocks, headings)
    _heading_tells(c, headings, words_total)
    _list_tells(c, blocks, items, paragraphs, words_total)
    _rhythm_tells(c, prose, paragraphs)
    _faq_tells(c, blocks, headings)

    by_family = {}
    for t in c.tells:
        by_family[t["family"]] = by_family.get(t["family"], 0) + 1
    return {
        "tells": c.tells,
        "summary": {
            "counts": dict(sorted(c.counts.items(), key=lambda kv: -kv[1])),
            "distinct": len(c.counts),
            "total": sum(c.counts.values()),
            "by_family": by_family,
            "words": words_total if prose else 0,
            "per_1000_words": round(sum(c.counts.values()) / words_total * 1000, 1) if prose else 0.0,
        },
    }


# ---------------------------------------------------------------------------
# Prose
# ---------------------------------------------------------------------------

def _prose_tells(c, blocks, prose, words_total):
    triads = []
    for i, b in prose:
        text = b.text
        for m in re.finditer(r"\s?—\s?|\s–\s", text):
            c.add("em_dash", "prose", "Em dash", "low",
                  "Use a comma, a full stop or brackets, or split the sentence.",
                  _snip(text, m.start(), m.end()), block=i,
                  detail="Common in machine-written copy; common in careful human copy too.")
        for m in _TRIAD_RX.finditer(text):
            # A comma just before means a longer list or a chain of clauses, not a triad.
            if "," not in text[max(0, m.start() - 40):m.start()].rsplit(".", 1)[-1]:
                triads.append((i, _snip(text, m.start(), m.end())))
        for m in _NOT_BUT_RX.finditer(text):
            c.add("not_x_but_y", "prose", "\"Not X, but Y\" reframe", "medium",
                  "Say what it is. Drop the thing it is not, unless someone really claimed it.",
                  _snip(text, m.start(), m.end()), block=i)
        for m in _STOCK_RX.finditer(text):
            c.add("stock_vocabulary", "prose", "Stock vocabulary", "medium",
                  "Replace with the plain word, or say the specific thing it stands for.",
                  _snip(text, m.start(), m.end(), 90), block=i, detail=m.group(0).lower())
        for m in _SIGNPOST_RX.finditer(text):
            c.add("signpost_phrase", "prose", "Signpost phrase", "medium",
                  "Cut the announcement and make the point.",
                  _snip(text, m.start(), m.end(), 100), block=i)
        sentences = split_sentences(text)
        for s in sentences:
            m = _TAIL_RX.search(s)
            if m:
                c.add("hedging_tail", "prose", "Trailing \"-ing\" clause", "medium",
                      "End the sentence at the fact. If the consequence matters, give it its "
                      "own sentence with a number or a name in it.",
                      _snip(s, m.start(), m.end()), block=i)
            m = _HEDGE_RX.search(s)
            if m:
                c.add("hedge", "prose", "Hedge", "low",
                      "Say what it depends on, or commit to the claim.",
                      _snip(s, m.start(), m.end(), 110), block=i)
        _three_beat(c, i, sentences)
        for a, b2 in zip(sentences, sentences[1:]):
            if _NOT_PAIR_RX.search(a) and _ITS_RX.search(b2) and len(a.split()) <= 12:
                c.add("not_x_but_y", "prose", "\"It's not X. It's Y.\" reframe", "medium",
                      "Say what it is. Drop the thing it is not, unless someone really claimed it.",
                      _snip(a + " " + b2), block=i)

    # Three-item lists are ordinary English. The tell is everything coming in threes.
    rate = len(triads) / words_total * 1000
    if len(triads) >= 3 and rate >= 4:
        for i, example in triads:
            c.add("rule_of_three", "prose", "Rule of three", "medium",
                  "Vary the count: two items, or four, or the one that matters.",
                  example, block=i,
                  detail=f"{len(triads)} three-item lists in {words_total} words "
                         f"({rate:.1f} per 1,000).")


def _three_beat(c, block_index, sentences):
    """Three short parallel sentences in a row ("It's fast. It's simple. It's yours.")
    or one sentence of three short parallel clauses ("No setup, no fees, no fuss.")."""
    run = []
    for s in sentences + [""]:
        n = len(s.split())
        if 1 <= n <= 5:
            run.append(s)
            continue
        if len(run) >= 3:
            firsts = [r.split()[0].lower().strip("'’") for r in run[:3]]
            lengths = [len(r.split()) for r in run[:3]]
            if len(set(firsts)) == 1 or max(lengths) - min(lengths) <= 1:
                c.add("three_beat", "prose", "Three-beat sentence run", "medium",
                      "Join them into one plain sentence, or keep the one that carries the point.",
                      " ".join(run[:3]), block=block_index)
        run = []
    for s in sentences:
        parts = [p.strip() for p in re.split(r",\s+(?:and\s+)?", s.rstrip(".!")) if p.strip()]
        if len(parts) == 3 and all(1 < len(p.split()) <= 4 for p in parts):
            firsts = {p.split()[0].lower() for p in parts}
            if len(firsts) == 1:
                c.add("three_beat", "prose", "Three-beat sentence", "medium",
                      "Join them into one plain sentence, or keep the one that carries the point.",
                      _snip(s), block=block_index)


# ---------------------------------------------------------------------------
# Sections: how they open and close
# ---------------------------------------------------------------------------

def _sections(blocks, headings):
    """[(heading index or None, [prose block indices])] in page order."""
    out, current, head = [], [], None
    for i, b in enumerate(blocks):
        if b.kind == "heading":
            if current or head is not None:
                out.append((head, current))
            head, current = i, []
        elif b.kind in PROSE_KINDS:
            current.append(i)
    if current or head is not None:
        out.append((head, current))
    return out


def _section_tells(c, blocks, headings):
    for head, body in _sections(blocks, headings):
        paras = [i for i in body if blocks[i].kind == "paragraph"]
        if not paras:
            continue
        first = split_sentences(blocks[paras[0]].text)
        last = split_sentences(blocks[paras[-1]].text)
        if first:
            opener = first[0]
            if _OPENER_RX.search(opener):
                c.add("stock_opener", "structure", "Stock opener", "medium",
                      "Start with the first real fact or the thing you did.",
                      _snip(opener), block=paras[0])
            elif head is not None:
                m = _DEFINE_RX.match(opener)
                subject = _content_words(m.group(1)) if m else set()
                if subject and subject & _content_words(blocks[head].text):
                    c.add("definition_opener", "structure", "Opener that defines the heading", "medium",
                          "The heading already named the topic. Open with what the reader "
                          "came for, and define the term only where it is first needed.",
                          _snip(opener), block=paras[0], blocks=[head, paras[0]])
        if last and (len(last) > 1 or len(paras) > 1) and _CLOSER_RX.search(last[-1]):
            c.add("tidy_closer", "structure", "Tidy section closer", "medium",
                  "Let the section end on its last fact. Cut the summing-up sentence.",
                  _snip(last[-1]), block=paras[-1])
    for i, b in headings:
        if _CONCLUSION_RX.match(b.text.strip()):
            c.add("conclusion_heading", "structure", "Wrap-up heading", "low",
                  "End on the last useful section, or give this one a heading that says "
                  "what it adds.", b.text, block=i)


# ---------------------------------------------------------------------------
# Headings
# ---------------------------------------------------------------------------

def _heading_tells(c, headings, words_total):
    real = [(i, b) for i, b in headings if not b.meta.get("inferred") or len(headings) > 1]
    for i, b in real:
        if _EMOJI_RX.search(b.text):
            c.add("emoji_heading", "structure", "Emoji in a heading", "medium",
                  "Remove the emoji; the heading text carries the meaning.", b.text, block=i)
    multi = [(i, b) for i, b in real if len(b.text.split()) >= 3]
    questions = [(i, b) for i, b in real if b.text.rstrip().endswith("?")]
    if len(questions) >= 2 and len(questions) / max(1, len(real)) >= 0.3:
        for i, b in questions:
            c.add("question_heading", "structure", "Question heading", "low",
                  "Use a heading that states the answer or names the thing.", b.text, block=i,
                  detail=f"{len(questions)} of {len(real)} headings are questions.")
    titled = [(i, b) for i, b in multi if _is_title_case(b.text)]
    if len(multi) >= 3 and len(titled) / len(multi) >= 0.6:
        for i, b in titled:
            c.add("title_case_heading", "structure", "Title Case Heading", "low",
                  "Sentence case reads as a person writing; capitalise only the first word "
                  "and proper nouns.", b.text, block=i,
                  detail=f"{len(titled)} of {len(multi)} multi-word headings are in title case.")
    if len(real) >= 4 and words_total / len(real) < 80:
        c.add("heading_density", "structure", "Heading every few lines", "medium",
              "Merge thin sections. A heading should earn a few paragraphs.",
              f"{len(real)} headings over {words_total} words", blocks=[i for i, _ in real],
              detail=f"One heading per {words_total // len(real)} words.")


# ---------------------------------------------------------------------------
# Lists
# ---------------------------------------------------------------------------

def _list_tells(c, blocks, items, paragraphs, words_total):
    lists = {}
    for i, b in items:
        lists.setdefault(b.meta.get("list", 0), []).append((i, b))
    for members in lists.values():
        led = [(i, b) for i, b in members if b.meta.get("bold_lead")]
        if len(led) >= 3 and len(led) / len(members) >= 0.6:
            c.add("bold_lead_bullets", "structure", "Bold lead-in bullets", "high",
                  "If each label needs a sentence, these are sub-headings with paragraphs. "
                  "If not, a plain list will do.",
                  f"{led[0][1].meta['bold_lead']}: {_snip(led[0][1].text, width=90)}",
                  block=led[0][0], blocks=[i for i, _ in led],
                  detail=f"{len(led)} of {len(members)} items open with a bold label.")
        emoji = [(i, b) for i, b in members
                 if b.meta.get("emoji_lead") or _EMOJI_RX.match(b.text.lstrip())]
        if len(emoji) >= 3:
            c.add("emoji_bullets", "structure", "Emoji bullets", "medium",
                  "Use ordinary bullets.", _snip(emoji[0][1].text, width=90),
                  block=emoji[0][0], blocks=[i for i, _ in emoji],
                  detail=f"{len(emoji)} items start with an emoji.")
        if len(members) == 3 and len(lists) >= 3:
            pass  # counted below as a page-level habit
    threes = [m for m in lists.values() if len(m) == 3]
    if len(lists) >= 3 and len(threes) / len(lists) >= 0.6:
        c.add("lists_of_three", "structure", "Lists of exactly three", "medium",
              "Let a list be as long as its contents: two, five, seven.",
              f"{len(threes)} of {len(lists)} lists have exactly three items",
              blocks=[i for m in threes for i, _ in m])
    led_paras = [(i, b) for i, b in paragraphs if b.meta.get("bold_lead")]
    if len(led_paras) >= 3:
        c.add("bold_lead_paragraphs", "structure", "Bold lead-in paragraphs", "medium",
              "A paragraph that opens with a bold label is a heading. Make it one, or "
              "write the paragraph without the label.",
              f"{led_paras[0][1].meta['bold_lead']}: {_snip(led_paras[0][1].text, width=90)}",
              block=led_paras[0][0], blocks=[i for i, _ in led_paras])
    list_words = sum(len(b.text.split()) for _, b in items)
    if len(items) >= 8 and list_words / words_total >= 0.4:
        c.add("bullet_density", "structure", "Mostly bullets", "medium",
              "Turn the lists that explain something into paragraphs; keep lists for "
              "things a reader scans.",
              f"{len(items)} list items carry {list_words * 100 // words_total}% of the words",
              blocks=[i for i, _ in items])


# ---------------------------------------------------------------------------
# Rhythm
# ---------------------------------------------------------------------------

def _rhythm_tells(c, prose, paragraphs):
    lengths = [len(b.text.split()) for _, b in paragraphs if len(b.text.split()) >= 8]
    if len(lengths) >= 5 and _cv(lengths) < 0.25:
        c.add("uniform_paragraphs", "structure", "Paragraphs all the same length", "medium",
              "Let paragraph length follow the content: a one-line paragraph next to a "
              "long one is normal.",
              f"{len(lengths)} paragraphs of {min(lengths)}-{max(lengths)} words",
              blocks=[i for i, b in paragraphs if len(b.text.split()) >= 8],
              detail=f"Coefficient of variation {_cv(lengths):.2f} (under 0.25 is very even).")
    sent_lengths = [len(s.split()) for _, b in prose for s in split_sentences(b.text)
                    if len(s.split()) >= 5]
    if len(sent_lengths) >= 8 and _cv(sent_lengths) < 0.3:
        c.add("uniform_sentences", "structure", "Sentences all the same length", "medium",
              "Mix short sentences with long ones.",
              f"{len(sent_lengths)} sentences, mean {statistics.fmean(sent_lengths):.0f} words",
              blocks=[i for i, _ in prose],
              detail=f"Coefficient of variation {_cv(sent_lengths):.2f} (under 0.30 is very even).")


# ---------------------------------------------------------------------------
# FAQ blocks that restate the body
# ---------------------------------------------------------------------------

def _faq_tells(c, blocks, headings):
    start = next((i for i, b in headings if _FAQ_RX.search(b.text)), None)
    if start is None:
        return
    level = blocks[start].level
    body = [split_sentences(b.text) for b in blocks[:start] if b.kind in PROSE_KINDS]
    body_sets = [_content_words(s) for group in body for s in group if len(s.split()) >= 5]
    restated, involved, example = 0, [start], ""
    answers = 0
    for i in range(start + 1, len(blocks)):
        b = blocks[i]
        if b.kind == "heading" and level and b.level and b.level <= level:
            break
        if b.kind not in PROSE_KINDS:
            continue
        answers += 1
        words = _content_words(b.text)
        if len(words) < 3:
            continue
        overlap = max((len(words & s) / len(words) for s in body_sets if s), default=0.0)
        if overlap >= 0.6:
            restated += 1
            involved.append(i)
            example = example or _snip(b.text)
    if restated >= 2 or (restated and restated == answers):
        c.add("faq_restates_body", "structure", "FAQ that repeats the article", "medium",
              "Keep only the questions the article did not already answer, or drop the block.",
              example, block=start, blocks=involved,
              detail=f"{restated} of {answers} answers reuse wording from the body above.")
