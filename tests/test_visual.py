from ai_detect.text import Document, Block
from ai_detect.visual import find_visual_tells, is_local_endpoint

def test_gradient_hero_flagged():
    visual = {"hero": {"rect": [0,0,100,100], "heading": "H", "centred": True, "buttons": 2, "gradient": True, "button_labels": ["A","B"]}}
    assert any(t["id"] == "gradient_hero" for t in find_visual_tells(visual))

def test_gradient_hero_clean():
    visual = {"hero": {"rect": [0,0,100,100], "heading": "H", "centred": True, "buttons": 2, "gradient": False, "button_labels": ["A","B"]}}
    assert not any(t["id"] == "gradient_hero" for t in find_visual_tells(visual))

def test_centred_hero_flagged():
    visual = {"hero": {"rect": [0,0,100,100], "heading": "H", "centred": True, "buttons": 2, "gradient": False, "button_labels": ["A","B"]}}
    assert any(t["id"] == "centred_hero" for t in find_visual_tells(visual))

def test_centred_hero_clean():
    visual = {"hero": {"rect": [0,0,100,100], "heading": "H", "centred": True, "buttons": 1, "gradient": False, "button_labels": ["A"]}}
    assert not any(t["id"] == "centred_hero" for t in find_visual_tells(visual))

def test_card_grid_of_three_flagged():
    items = [{"rect": [0,0,10,10], "heading": "H", "icon": False, "words": 10, "blurb_words": 10} for _ in range(3)]
    visual = {"groups": [{"rect": [0,0,100,100], "count": 3, "same_row": True, "items": items}]}
    assert any(t["id"] == "card_grid_of_three" for t in find_visual_tells(visual))

def test_card_grid_of_three_clean():
    items = [{"rect": [0,0,10,10], "heading": "H", "icon": False, "words": 10, "blurb_words": 10} for _ in range(4)]
    visual = {"groups": [{"rect": [0,0,100,100], "count": 4, "same_row": True, "items": items}]}
    assert not any(t["id"] == "card_grid_of_three" for t in find_visual_tells(visual))

def test_icon_feature_grid_flagged():
    items = [{"rect": [0,0,10,10], "heading": "H", "icon": True, "words": 10, "blurb_words": 10} for _ in range(4)]
    visual = {"groups": [{"rect": [0,0,100,100], "count": 4, "same_row": True, "items": items}]}
    assert any(t["id"] == "icon_feature_grid" for t in find_visual_tells(visual))

def test_icon_feature_grid_clean():
    items = [{"rect": [0,0,10,10], "heading": "H", "icon": False, "words": 10, "blurb_words": 10} for _ in range(4)]
    visual = {"groups": [{"rect": [0,0,100,100], "count": 4, "same_row": True, "items": items}]}
    assert not any(t["id"] == "icon_feature_grid" for t in find_visual_tells(visual))

def test_uniform_section_rhythm_flagged():
    sections = [{"rect": [0,0,100,100], "centred": False} for _ in range(4)]
    assert any(t["id"] == "uniform_section_rhythm" for t in find_visual_tells({"sections": sections}))

def test_uniform_section_rhythm_clean():
    sections = [{"rect": [0,0,100,100], "centred": False}, {"rect": [0,0,100,200], "centred": False}, {"rect": [0,0,100,300], "centred": False}, {"rect": [0,0,100,400], "centred": False}]
    assert not any(t["id"] == "uniform_section_rhythm" for t in find_visual_tells({"sections": sections}))

def test_ai_image_candidate_flagged():
    img = {"rect": [0,0,10,10], "src": "dalle-3-hero.png", "alt": "Hero", "title": "T", "caption": "C"}
    assert any(t["id"] == "ai_image_candidate" for t in find_visual_tells({"images": [img]}))

def test_ai_image_candidate_clean():
    img = {"rect": [0,0,10,10], "src": "hero.png", "alt": "Hero", "title": "T", "caption": "C"}
    assert not any(t["id"] == "ai_image_candidate" for t in find_visual_tells({"images": [img]}))

def test_stock_image_candidate_flagged():
    img = {"rect": [0,0,10,10], "src": "shutterstock.png", "alt": "Hero", "title": "T", "caption": "C"}
    assert any(t["id"] == "stock_image_candidate" for t in find_visual_tells({"images": [img]}))

def test_stock_image_candidate_clean():
    img = {"rect": [0,0,10,10], "src": "hero.png", "alt": "Hero", "title": "T", "caption": "C"}
    assert not any(t["id"] == "stock_image_candidate" for t in find_visual_tells({"images": [img]}))

def test_wall_of_bullets_flagged():
    blocks = [Block("list_item", "text", 0, {"list": 1, "rect": [0, y, 300, 20]}) for y in range(7)]
    assert any(t["id"] == "wall_of_bullets" for t in find_visual_tells({}, Document(blocks=blocks)))

def test_wall_of_bullets_clean():
    blocks = [Block("list_item", "text", 0, {"list": 1, "rect": [0, y, 300, 20]}) for y in range(6)]
    assert not any(t["id"] == "wall_of_bullets" for t in find_visual_tells({}, Document(blocks=blocks)))

def test_icon_bullets_flagged():
    blocks = [Block("list_item", "text", 0, {"list": 1, "rect": [0, y, 300, 20], "icon_lead": True}) for y in range(3)]
    assert any(t["id"] == "icon_bullets" for t in find_visual_tells({}, Document(blocks=blocks)))

def test_icon_bullets_clean():
    blocks = [Block("list_item", "text", 0, {"list": 1, "rect": [0, y, 300, 20]}) for y in range(3)]
    assert not any(t["id"] == "icon_bullets" for t in find_visual_tells({}, Document(blocks=blocks)))

def test_empty_visual():
    assert find_visual_tells({}) == []

def test_visual_structure():
    visual = {"hero": {"rect": [0,0,100,100], "heading": "H", "centred": True, "buttons": 2, "gradient": True, "button_labels": ["A","B"]}}
    tells = find_visual_tells(visual)
    for t in tells:
        assert t["family"] == "visual"
        assert "rect" in t

def test_is_local_endpoint_true():
    assert is_local_endpoint("http://127.0.0.1:8000/v1")

def test_is_local_endpoint_false():
    assert not is_local_endpoint("https://api.example.com/v1")

def test_ai_image_detail():
    img = {"rect": [0,0,10,10], "src": "dalle-3-hero.png", "alt": "Hero", "title": "T", "caption": "C"}
    tells = find_visual_tells({"images": [img]})
    assert "lead" in [t["detail"] for t in tells if t["id"] == "ai_image_candidate"][0]
