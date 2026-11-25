"""Layout checks by bounding box: nothing is drawn over its neighbour.

2.0.0 drew the Sentences table of a five-model scan wider than its grid column,
so its last columns were printed over the side panel. These tests measure the
rendered boxes instead of looking for elements, at the widths people use.
"""

import pytest

from test_dashboard import TEXT, scan_url, unexpected

FIVE = ["gpttrace-150m", "desklib", "gpttrace-1b", "tabularis", "light"]
WIDTHS = [1100, 1280, 1440, 1920]

# Several sentences, one of them long, so the first column wants room.
LONG_TEXT = TEXT + " " + (
    "Distillation trains a small model on a big model's answers until the small model writes "
    "answers in the big model's pattern, which is cheaper to run on hardware you already own. "
    "Engineers call the big model the teacher and the small one the student. "
    "Furthermore, the comprehensive platform provides seamless support for every team. "
    "You choose how small the student is, so you can size it for the budget it has to run on. "
    "Every call costs money and waits on someone else's servers. "
    "Additionally, the service provides a comprehensive overview of the whole process.")

# Every problem of the "drawn outside its box" class on the current page:
# * the document scrolls sideways;
# * a table is wider than the box it sits in, and that box does not scroll;
# * something in the left column of a result reaches into the side panel.
AUDIT = """() => {
  const out = [];
  const root = document.documentElement;
  if (root.scrollWidth > root.clientWidth + 1) out.push(`page scrolls sideways: ${root.scrollWidth} > ${root.clientWidth}`);
  const scrolls = (el) => ['auto', 'scroll'].includes(getComputedStyle(el).overflowX);
  for (const t of document.querySelectorAll('main table')) {
    const box = t.parentElement.getBoundingClientRect(), r = t.getBoundingClientRect();
    if (r.right > box.right + 1 && !scrolls(t.parentElement)) out.push(`table wider than its box: ${Math.round(r.right)} > ${Math.round(box.right)}`);
  }
  const side = document.querySelector('.side'), left = document.querySelector('#left');
  if (side && left) {
    const s = side.getBoundingClientRect();
    for (const el of left.querySelectorAll('*')) {
      const r = el.getBoundingClientRect();
      if (!r.width || !r.height) continue;
      if (r.left < s.right - 1 && r.right > s.left + 1 && r.top < s.bottom - 1 && r.bottom > s.top + 1) {
        out.push(`${el.tagName} "${(el.textContent || '').trim().slice(0, 30)}" overlaps the side panel`);
        if (out.length > 8) break;
      }
    }
  }
  return out;
}"""

# After scrolling the table's own box fully to the right: is the last column
# header inside that box and inside the window?
LAST_HEADER = """() => {
  const wrap = document.querySelector('#left .tablewrap');
  wrap.scrollLeft = wrap.scrollWidth;
  const th = wrap.querySelector('thead th:last-child').getBoundingClientRect();
  const w = wrap.getBoundingClientRect();
  return { text: wrap.querySelector('thead th:last-child').textContent, left: th.left, right: th.right,
           wrapLeft: w.left, wrapRight: w.right, win: document.documentElement.clientWidth,
           scrolled: wrap.scrollLeft };
}"""


def audit(page):
    return page.evaluate(AUDIT)


class FakeScorer:
    """Stands in for GPT-2: four-figure perplexities, as real pages produce."""

    def nll(self, text):
        return 7.1 * max(len(text.split()), 3), max(len(text.split()), 3)


def scan(page, models, perplexity=False, text=LONG_TEXT):
    for box in page.locator("#model-picker input[type='checkbox']").all():
        want = box.get_attribute("value") in models
        if box.is_checked() != want:
            box.set_checked(want)
    page.set_checked("#opt-ppl", perplexity)
    page.fill("#text", text)
    page.click("#scan-form .primary")
    page.wait_for_selector(".verdict .label", timeout=30000)


@pytest.fixture
def five_ready(ctl, monkeypatch):
    from ai_detect import perplexity
    monkeypatch.setattr(perplexity, "get_scorer", lambda device=None: FakeScorer())
    before = set(ctl["ready"])
    ctl["ready"] |= set(FIVE)
    yield
    ctl["ready"].clear()
    ctl["ready"] |= before


def check_sentences_view(page, width, last_header):
    page.set_viewport_size({"width": width, "height": 900})
    page.click('#view button[data-v="table"]')
    page.wait_for_selector("#left table")
    assert audit(page) == [], f"at {width}px"
    # No table cell shares any area with the side panel.
    side = page.locator(".side").bounding_box()
    for cell in page.locator("#left th, #left td").all():
        c = cell.bounding_box()
        apart = (c["x"] + c["width"] <= side["x"] + 1 or c["x"] >= side["x"] + side["width"] - 1
                 or c["y"] + c["height"] <= side["y"] + 1 or c["y"] >= side["y"] + side["height"] - 1)
        assert apart, f"at {width}px a cell overlaps the side panel: {cell.inner_text()!r}"
    # The side panel is under the table, not beside it.
    table = page.locator("#left .tablewrap").bounding_box()
    assert side["y"] >= table["y"] + table["height"] - 1
    # The last column can be seen, after scrolling the table's own box if need be.
    h = page.evaluate(LAST_HEADER)
    assert h["text"] == last_header
    assert h["left"] >= h["wrapLeft"] - 1 and h["right"] <= h["wrapRight"] + 1, h
    assert h["right"] <= h["win"] + 1, h


def test_sentences_table_of_five_models_with_perplexity_stays_off_the_side_panel(page, five_ready):
    scan(page, FIVE, perplexity=True)
    for width in (1440, 1100):
        check_sentences_view(page, width, "Perplexity")
    heads = [t.lower() for t in page.locator("#left thead th").all_inner_texts()]
    assert heads[0] == "sentence" and sorted(heads[1:6]) == sorted(FIVE)      # in the order ticked
    assert heads[6:] == ["agree", "combined", "perplexity"]
    assert unexpected(page) == []


@pytest.mark.parametrize("models, ppl, last", [(["gpttrace-150m"], False, "gpttrace-150m"),
                                               (FIVE, True, "Perplexity")])
def test_sentences_table_never_overlaps_from_1100_to_1920(page, five_ready, models, ppl, last):
    scan(page, models, perplexity=ppl)
    for width in WIDTHS:
        check_sentences_view(page, width, last)
    assert unexpected(page) == []


def test_text_view_keeps_the_side_panel_beside_the_text(page, five_ready):
    scan(page, FIVE, perplexity=True)
    for width in (1100, 1440):
        page.set_viewport_size({"width": width, "height": 900})
        page.click('#view button[data-v="table"]')
        page.click('#view button[data-v="text"]')        # and back: the stacking is undone
        left, side = page.locator("#left").bounding_box(), page.locator(".side").bounding_box()
        assert side["x"] >= left["x"] + left["width"], f"at {width}px"
        assert abs(side["width"] - 400) < 2
        assert audit(page) == [], f"at {width}px"


def test_clicking_a_table_row_shows_its_detail_and_marks_the_row(page, five_ready):
    scan(page, FIVE, perplexity=True)
    page.click('#view button[data-v="table"]')
    page.click("#left tr.link >> nth=2")
    assert "model scores" in page.inner_text("#panel").lower()
    assert page.locator("#left tr.on").count() == 1
    page.wait_for_function("""() => { const r = document.querySelector('#panel').getBoundingClientRect();
        return r.top < window.innerHeight && r.bottom > 0; }""")
    assert unexpected(page) == []


def test_side_tabs_fit_their_panel_at_1440(page, five_ready):
    scan(page, FIVE, perplexity=True)
    side = page.locator(".side")
    for name in ("sentence", "tells", "rewrite", "models", "signals"):
        page.click(f'.side [role="tab"][data-p="{name}"]')
        assert audit(page) == [], name
        # Nothing in the panel is wider than the panel: it has no sideways scroll.
        assert side.evaluate("e => e.scrollWidth <= e.clientWidth + 1"), name
    page.click("span.s:not(.skip) >> nth=0")              # the Sentence tab with a sentence chosen
    assert audit(page) == []
    assert side.evaluate("e => e.scrollWidth <= e.clientWidth + 1")
    assert unexpected(page) == []


def test_page_view_fits_at_1440(page, site):
    scan_url(page, site + "/slop_landing.html")
    page.click('#view button[data-v="page"]')
    page.wait_for_selector("#shot img")
    assert audit(page) == []
    left, side = page.locator("#left").bounding_box(), page.locator(".side").bounding_box()
    assert side["x"] >= left["x"] + left["width"]


def test_other_pages_fit_at_1440(page, site, five_ready):
    home = page.url.split("#")[0]
    scan(page, FIVE, perplexity=True)                     # something long for History to list
    page.goto(home + "#/compare")
    page.wait_for_selector("#compare-form")
    assert audit(page) == [], "compare form"
    page.fill("#cmp-a", LONG_TEXT)
    page.fill("#cmp-b", "My brother thinks it's too slow, and I don't love the price either, to be honest.")
    page.click("#compare-form .primary")
    page.wait_for_selector("#compare-result table", timeout=60000)
    assert audit(page) == [], "compare result"

    page.goto(home + "#/batch")
    page.wait_for_selector("#batch-form")
    page.fill("#batch-items", f"{site}/slop_landing.html\n{site}/plain_article.html\n"
                              "C:/definitely/missing/" + "a-very-long-folder-name/" * 8 + "file.md")
    page.click("#batch-form .primary")
    page.wait_for_function("() => document.querySelectorAll('#batch-result tbody tr').length >= 3",
                           timeout=120000)
    assert audit(page) == [], "batch"

    page.goto(home + "#/history")
    page.wait_for_selector("#h-on")
    assert page.locator("tbody tr.link").count() >= 1
    assert audit(page) == [], "history"

    page.goto(home + "#/models")
    page.wait_for_selector("main table")
    assert audit(page) == [], "models"

    page.goto(home + "#/")
    page.wait_for_selector("#scan-form")
    assert audit(page) == [], "scan form"
    assert unexpected(page) == []
