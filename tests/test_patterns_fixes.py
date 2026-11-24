from ai_detect.patterns import diagnose_sentence, count_pattern_totals

def _get_patterns(text):
    findings = diagnose_sentence(text)
    return {f["pattern"] for f in findings}

def test_no_false_positives_for_common_nouns():
    patterns = _get_patterns("It has three new features and two email addresses.")
    assert "missing_contraction" not in patterns
    assert "formal_verb" not in patterns

def test_missing_contraction_detected():
    assert "missing_contraction" in _get_patterns("It has been improved.")

def test_formal_verb_comprehensive():
    assert "formal_verb" in _get_patterns("The base offers comprehensive software support.")
    assert "formal_verb" in _get_patterns("We provide tools.")
    assert "formal_verb" in _get_patterns("They are providing tools.")
    assert "formal_verb" in _get_patterns("It utilises the cache.")
    assert "formal_verb" in _get_patterns("It utilizes the cache.")

def test_ai_slop_detected():
    assert "ai_slop" in _get_patterns("Leveraging data is common.")

def test_formal_transition_curly_apostrophe():
    assert "formal_transition" in _get_patterns("It’s important to note that prices vary.")

def test_findings_have_valid_offsets():
    findings = diagnose_sentence("It has been improved. A wide range of options.")
    for f in findings:
        assert isinstance(f["start"], int)
        assert isinstance(f["end"], int)
        assert "It has been improved. A wide range of options."[f["start"]:f["end"]]

def test_vague_abstraction_count():
    findings = [f for f in diagnose_sentence("a wide range of options") if f["pattern"] == "vague_abstraction"]
    assert len(findings) == 1

def test_count_pattern_totals_label_filter():
    data = [
        {"label": "AI", "diagnostics": [{"pattern": "formal_verb"}, {"pattern": "formal_verb"}]},
        {"label": "Human", "diagnostics": [{"pattern": "formal_verb"}]},
        None
    ]
    totals = count_pattern_totals(data, only_label="AI")
    assert totals.get("formal_verb") == 2
