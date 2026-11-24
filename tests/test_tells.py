import re
from ai_detect.text import parse_text
from ai_detect.tells import find_tells, MAX_PER_TELL

def ids(md):
    return {t["id"] for t in find_tells(parse_text(md))["tells"]}

def test_em_dash_flagged():
    assert "em_dash" in ids("Fast — and safe.")

def test_em_dash_clean():
    assert "em_dash" not in ids("Fast, and safe.")

def test_rule_of_three_flagged():
    text = "We have fast, simple, and secure. Our tool is fast, simple, and secure. It is fast, simple, and secure."
    assert "rule_of_three" in ids(text)

def test_rule_of_three_clean():
    assert "rule_of_three" not in ids("We have fast and secure.")

def test_three_beat_flagged():
    assert "three_beat" in ids("It is fast. It is cheap. It is good.")

def test_three_beat_clean():
    assert "three_beat" not in ids("It is fast. It is good.")

def test_not_x_but_y_flagged():
    assert "not_x_but_y" in ids("It is not just a tool, but a whole platform for teams.")

def test_not_x_but_y_clean():
    assert "not_x_but_y" not in ids("It is fast.")

def test_stock_vocabulary_flagged():
    assert "stock_vocabulary" in ids("It is a beacon.")

def test_stock_vocabulary_clean():
    assert "stock_vocabulary" not in ids("It is a light.")

def test_signpost_phrase_flagged():
    assert "signpost_phrase" in ids("Let's dive in.")

def test_signpost_phrase_clean():
    assert "signpost_phrase" not in ids("Let us start.")

def test_hedging_tail_flagged():
    assert "hedging_tail" in ids("We run tests daily, ensuring accuracy.")

def test_hedging_tail_clean():
    assert "hedging_tail" not in ids("We run tests daily.")

def test_hedge_flagged():
    assert "hedge" in ids("It may vary.")

def test_hedge_clean():
    assert "hedge" not in ids("It varies.")

def test_stock_opener_flagged():
    assert "stock_opener" in ids("In today's world, we act.")

def test_stock_opener_clean():
    assert "stock_opener" not in ids("We act today.")

def test_definition_opener_flagged():
    assert "definition_opener" in ids("## Pricing\n\nPricing is a plan.")

def test_definition_opener_clean():
    assert "definition_opener" not in ids("## Pricing\n\nWe start plans at ten dollars.")

def test_tidy_closer_flagged():
    assert "tidy_closer" in ids("## End\n\nWe act. In short, it is done.")

def test_tidy_closer_clean():
    assert "tidy_closer" not in ids("## End\n\nWe act. It is done.")

def test_conclusion_heading_flagged():
    assert "conclusion_heading" in ids("## Conclusion\n\nText here.")

def test_conclusion_heading_clean():
    assert "conclusion_heading" not in ids("## Final Notes\n\nText here.")

def test_emoji_heading_flagged():
    assert "emoji_heading" in ids("## 🚀 Go\n\nText.")

def test_emoji_heading_clean():
    assert "emoji_heading" not in ids("## Go\n\nText.")

def test_question_heading_flagged():
    assert "question_heading" in ids("## Why?\n\n\n## How?\n\n\n## When?\n\nText.")

def test_question_heading_clean():
    assert "question_heading" not in ids("## Why\n\n\n## How\n\n\n## When\n\nText.")

def test_title_case_heading_flagged():
    assert "title_case_heading" in ids("## One Two Three\n\n\n## Four Five Six\n\n\n## Seven Eight Nine\n\n\n## Ten Eleven Twelve\n\nText.")

def test_title_case_heading_clean():
    assert "title_case_heading" not in ids("## one two three\n\n\n## four five six\n\n\n## seven eight nine\n\n\n## ten eleven twelve\n\nText.")

def test_heading_density_flagged():
    assert "heading_density" in ids("## A\n\nText.\n\n\n## B\n\nText.\n\n\n## C\n\nText.\n\n\n## D\n\nText.")

def test_heading_density_clean():
    assert "heading_density" not in ids("## A\n\n" + "word " * 100 + "End.\n\n\n## B\n\n" + "word " * 100 + "End.")

def test_bold_lead_bullets_flagged():
    assert "bold_lead_bullets" in ids("- **A:** text here now\n- **B:** text here now\n- **C:** text here now")

def test_bold_lead_bullets_clean():
    assert "bold_lead_bullets" not in ids("- A: text here now\n- B: text here now\n- C: text here now")

def test_emoji_bullets_flagged():
    assert "emoji_bullets" in ids("- 🚀 text here now\n- ✨ text here now\n- ✅ text here now")

def test_emoji_bullets_clean():
    assert "emoji_bullets" not in ids("- text here now\n- text here now\n- text here now")

def test_lists_of_three_flagged():
    text = "- a\n- b\n- c\n\n- a\n- b\n- c\n\n- a\n- b\n- c"
    assert "lists_of_three" in ids(text)

def test_lists_of_three_clean():
    text = "- a\n- b\n- c\n- d\n\n- a\n- b\n\n- a\n- b"
    assert "lists_of_three" not in ids(text)

def test_bold_lead_paragraphs_flagged():
    text = "\n\n".join([f"**A{i}:** text here now" for i in range(4)])
    assert "bold_lead_paragraphs" in ids(text)

def test_bold_lead_paragraphs_clean():
    text = "\n\n".join([f"A{i} text here now" for i in range(4)])
    assert "bold_lead_paragraphs" not in ids(text)

def test_bullet_density_flagged():
    text = "Intro text here.\n\n" + "\n".join([f"- item {i} words here" for i in range(10)])
    assert "bullet_density" in ids(text)

def test_bullet_density_clean():
    text = "Intro text here.\n\n- item 1 words\n\n" + "\n\n".join([f"Para {i} text here now" for i in range(10)])
    assert "bullet_density" not in ids(text)

def test_uniform_paragraphs_flagged():
    text = "\n\n".join(["word " * 10 + "end" for _ in range(5)])
    assert "uniform_paragraphs" in ids(text)

def test_uniform_paragraphs_clean():
    text = "\n\n".join(["word " * i + "end" for i in range(8, 13)])
    assert "uniform_paragraphs" not in ids(text)

def test_uniform_sentences_flagged():
    text = " ".join(["Word " * 5 + "end." for _ in range(10)])
    assert "uniform_sentences" in ids(text)

def test_uniform_sentences_clean():
    text = " ".join(["word " * (i + 2) + "end." for i in range(10)])
    assert "uniform_sentences" not in ids(text)

def test_faq_restates_body_flagged():
    body = "The product is fast and secure for users."
    text = f"{body}\n\n\n## FAQ\n\nThe product is fast and secure for users."
    assert "faq_restates_body" in ids(text)

def test_faq_restates_body_clean():
    body = "The product is fast and secure for users."
    text = f"{body}\n\n\n## FAQ\n\nIs it reliable? Yes, it is."
    assert "faq_restates_body" not in ids(text)

def test_tell_structure():
    doc = parse_text("A beacon — fast.")
    t = find_tells(doc)["tells"][0]
    for k in ("id", "family", "label", "severity", "block", "blocks", "example", "suggestion", "detail"):
        assert k in t

def test_summary_structure():
    doc = parse_text("A beacon — fast.")
    s = find_tells(doc)["summary"]
    assert "counts" in s and "total" in s and "per_1000_words" in s

def test_empty_doc():
    assert find_tells(parse_text(""))["tells"] == []

def test_max_per_tell():
    md = " ".join(["word" for _ in range(500)]) + " " + " — ".join(["x"] * 20)
    r = find_tells(parse_text(md))
    em_dashes = [t for t in r["tells"] if t["id"] == "em_dash"]
    assert len(em_dashes) == MAX_PER_TELL
    assert r["summary"]["counts"]["em_dash"] == 19
