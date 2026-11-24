from ai_detect.text import parse_text, strip_inline, sent_tokenize

def test_markdown_heading_structure():
    doc = parse_text("# Title\nSome text that runs on and ends properly.")
    assert doc.blocks[0].kind == "heading"
    assert doc.blocks[1].kind == "paragraph"

def test_list_items_shared_meta():
    doc = parse_text("- one\n- two")
    assert doc.blocks[0].meta["list"] == doc.blocks[1].meta["list"]
    assert doc.blocks[0].kind == "list_item"

def test_bold_lead_metadata():
    doc = parse_text("- **Speed:** it is fast")
    assert doc.blocks[0].meta.get("bold_lead") == "Speed"

def test_fenced_code_excluded_from_tokenize():
    doc = parse_text("```\nfoo = 1\n```")
    assert doc.blocks[0].kind == "code"
    assert "foo" not in " ".join(sent_tokenize("```\nfoo = 1\n```"))

def test_table_structure():
    doc = parse_text("| A | B |\n|---|---|\n| 1 | 2 |")
    table_blocks = [b for b in doc.blocks if b.kind == "table"]
    assert len(table_blocks) == 1
    assert len(table_blocks[0].meta["rows"]) == 2

def test_front_matter_removed():
    doc = parse_text("---\ntitle: test\n---\nHello")
    assert "title" not in doc.text
    assert "Hello" in doc.text

def test_inferred_heading():
    doc = parse_text("Install")
    assert doc.blocks[0].kind == "heading"
    assert doc.blocks[0].meta.get("inferred") is True

def test_split_sentences_abbreviations():
    text = "e.g. on a Mac. Dr. Smith. \"Really?\" he asked. J. Smith. The U.S. Army came. One thing. Two things! Three things?"
    sents = sent_tokenize(text)
    assert "e.g. on a Mac." in sents
    assert "Dr. Smith." in sents
    assert '"Really?" he asked.' in sents
    assert "J. Smith." in sents
    assert "The U.S. Army came." in sents
    assert len([s for s in sents if s in ("One thing.", "Two things!", "Three things?")]) == 3

def test_strip_inline_markup():
    text = "[link](url) **bold** `code`"
    assert strip_inline(text) == "link bold code"

def test_sent_tokenize_heading_isolation():
    text = "## Install\n\nRun the thing."
    assert sent_tokenize(text) == ["Install", "Run the thing."]
