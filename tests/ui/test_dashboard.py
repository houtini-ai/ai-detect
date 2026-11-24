"""Browser tests for the dashboard: every control, plus the error paths.

Needs Playwright and Chromium (the whole folder is skipped without them). No
model is loaded: see conftest.py. Test cases were drafted by a local model from
a written list of controls and then corrected against the running UI.
"""

EXPECTED_HTTP = "Failed to load resource"  # the browser logs our own 400/404 answers


def unexpected(page):
    return [e for e in page.errors if EXPECTED_HTTP not in e]



TEXT = ("Furthermore, the platform provides a seamless experience for modern teams. "
        "Additionally, it provides comprehensive support across multiple regions. "
        "I don't love the price, though, and my brother thinks it's too slow.")


def row_for(page, model_id):
    return page.locator("tbody tr", has_text=model_id).first


def scan_url(page, site_url):
    page.goto(page.url.replace("#/", "#/").split("#")[0] + "#/")
    page.wait_for_selector("#scan-form")
    page.click('#scan-form [role="tab"][data-src="url"]')
    page.fill("#url", site_url)
    page.click("#scan-form .primary")
    page.wait_for_selector(".verdict .label", timeout=60000)


def test_nav_links_switch_pages(page):
    for nav, h1 in [("compare", "Compare two versions"), ("batch", "Batch scan"),
                     ("history", "History"), ("models", "Models"), ("scan", "Scan a draft")]:
        page.click(f'.top nav a[data-nav="{nav}"]')
        page.wait_for_function("t => document.querySelector('h1') && document.querySelector('h1').innerText === t", arg=h1)
        assert page.get_attribute(f'.top nav a[data-nav="{nav}"]', "aria-current") == "page"
    assert unexpected(page) == []


def test_theme_toggle_persists(page):
    page.click("#theme")
    cls1 = page.get_attribute("html", "class")
    page.click("#theme")
    cls2 = page.get_attribute("html", "class")
    assert cls1 != cls2
    page.reload()
    page.wait_for_selector("#scan-form")
    assert page.get_attribute("html", "class") == cls2
    assert unexpected(page) == []


def test_source_tabs_switch_panes(page):
    page.click('#scan-form [role="tab"][data-src="url"]')
    assert not page.is_hidden("#url")
    assert page.is_hidden("#text")
    page.click('#scan-form [role="tab"][data-src="file"]')
    assert not page.is_hidden("#drop")
    page.click('#scan-form [role="tab"][data-src="text"]')
    assert not page.is_hidden("#text")
    assert unexpected(page) == []


def test_text_scan_shows_verdict_and_highlights(scanned):
    assert scanned.inner_text(".verdict .label")
    assert scanned.locator("span.s.h4").count() >= 1
    assert scanned.locator("span.s.h0").count() >= 1
    assert "%" in scanned.inner_text(".verdict .stat .v")
    assert unexpected(scanned) == []


def test_click_sentence_opens_detail(scanned):
    target = scanned.locator("span.s.h4").first
    target.click()
    assert "model scores" in scanned.inner_text("#panel").lower()
    assert "on" in (target.get_attribute("class") or "")
    assert unexpected(scanned) == []


def test_keyboard_enter_on_sentence(scanned):
    target = scanned.locator("span.s.h4").first
    target.focus()
    target.press("Enter")
    assert "model scores" in scanned.inner_text("#panel").lower()
    assert unexpected(scanned) == []


def test_side_tabs_all_render(scanned):
    for p in ("sentence", "tells", "rewrite", "models", "signals"):
        scanned.click(f'.side [role="tab"][data-p="{p}"]')
        assert scanned.inner_text("#panel")
        assert scanned.get_attribute(f'.side [role="tab"][data-p="{p}"]', "aria-selected") == "true"
    assert unexpected(scanned) == []


def test_view_switch_text_and_table(scanned):
    scanned.click('#view button[data-v="table"]')
    assert not scanned.is_hidden("#left table")
    assert "sentence" in scanned.inner_text("#left table th").lower()
    scanned.click("#left tr.link")
    assert "model scores" in scanned.inner_text("#panel").lower()
    scanned.click('#view button[data-v="text"]')
    assert not scanned.is_hidden(".doc")
    assert unexpected(scanned) == []


def test_rewrite_tab_lists_suggestions(scanned):
    scanned.click('.side [role="tab"][data-p="rewrite"]')
    assert scanned.locator(".card .fix").count() >= 1
    assert unexpected(scanned) == []


def test_exports_download(scanned):
    for text, ext in [("Report (HTML)", ".html"), ("CSV", ".csv"), ("JSON", ".json")]:
        with scanned.expect_download() as dl:
            scanned.click(f".toolbar a:has-text('{text}')")
        assert dl.value.suggested_filename.endswith(ext)
    assert unexpected(scanned) == []


def test_ensemble_two_models_shows_agreement(page):
    page.check("#model-picker input[value='light']")
    page.fill("#text", TEXT)
    page.click("#scan-form .primary")
    page.wait_for_selector(".verdict .label", timeout=30000)
    page.click('#view button[data-v="table"]')
    assert "agree" in page.inner_text("#left table thead").lower()
    assert "combined" in page.inner_text("#left table thead").lower()
    page.goto(page.url.split("#")[0] + "#/")
    page.wait_for_selector("#scan-form")
    page.uncheck("#model-picker input[value='light']")
    assert unexpected(page) == []


def test_more_than_five_models_is_capped(page):
    boxes = page.locator("#model-picker input[type='checkbox']")
    n = boxes.count()
    for i in range(n):
        if not boxes.nth(i).is_checked():
            boxes.nth(i).click()  # the sixth click is undone by the cap
    assert page.locator("#model-picker input:checked").count() == 5
    for i in range(n):
        if boxes.nth(i).is_checked() and boxes.nth(i).get_attribute("value") != "desklib":
            boxes.nth(i).uncheck()
    assert unexpected(page) == []


def test_url_scan_shows_page_view_and_tells(page, site):
    scan_url(page, site + "/slop_landing.html")
    assert page.locator('#view button[data-v="page"]').count() >= 1
    page.click('#view button[data-v="page"]')
    page.wait_for_function("() => { const i = document.querySelector('#shot img'); return i && i.complete && i.naturalHeight > 0; }", timeout=15000)
    assert page.locator("#shot .box").count() >= 1
    page.click("#shot .box")
    assert page.locator(".card.on").count() >= 1
    page.click('.side [role="tab"][data-p="tells"]')
    assert page.locator(".card[data-t]").count() >= 5
    assert unexpected(page) == []


def test_tell_click_highlights_block(page, site):
    scan_url(page, site + "/slop_landing.html")
    page.click('.side [role="tab"][data-p="tells"]')
    page.click(".card[data-t]")
    assert page.locator(".blk.lit").count() >= 1 or page.locator(".box.on").count() >= 1
    assert unexpected(page) == []


def test_file_upload_scan(page):
    page.click('#scan-form [role="tab"][data-src="file"]')
    page.set_input_files("#file", {"name": "note.md", "mimeType": "text/markdown", "buffer": TEXT.encode()})
    assert "note.md" in page.inner_text("#file-name")
    page.click("#scan-form .primary")
    page.wait_for_selector(".verdict .label", timeout=30000)
    assert "note.md" in page.inner_text(".verdict .src")
    assert unexpected(page) == []


def test_empty_text_shows_error(page):
    page.fill("#text", "")
    page.click("#scan-form .primary")
    page.wait_for_selector("#scan-progress .error", timeout=30000)
    assert "Nothing to scan" in page.inner_text("#scan-progress .error")
    assert not page.is_disabled("#scan-form .primary")
    assert unexpected(page) == []


def test_bad_url_shows_error(page):
    page.click('#scan-form [role="tab"][data-src="url"]')
    page.evaluate("document.querySelector('#url').type='text'")
    page.fill("#url", "ftp://example.com/x")
    page.click("#scan-form .primary")
    page.wait_for_selector("#scan-progress .error", timeout=30000)
    assert unexpected(page) == []


def test_unreachable_url_shows_error(page):
    page.click('#scan-form [role="tab"][data-src="url"]')
    page.fill("#url", "http://127.0.0.1:9/nothing")
    page.click("#scan-form .primary")
    page.wait_for_selector(".error", timeout=60000)
    assert not page.is_disabled("#scan-form .primary")
    assert unexpected(page) == []


def test_private_url_is_refused_with_the_reason(page, monkeypatch):
    monkeypatch.delenv("AI_DETECT_ALLOW_PRIVATE_URLS")
    page.click('#scan-form [role="tab"][data-src="url"]')
    page.fill("#url", "http://127.0.0.1:9/nothing")
    page.click("#scan-form .primary")
    page.wait_for_selector(".error", timeout=60000)
    message = page.inner_text(".error")
    assert "loopback" in message and "AI_DETECT_ALLOW_PRIVATE_URLS" in message
    assert not page.is_disabled("#scan-form .primary")
    assert unexpected(page) == []


def test_compare_shows_delta_table(page):
    page.goto(page.url.split("#")[0] + "#/compare")
    page.wait_for_selector("#compare-form")
    page.fill("#cmp-a", TEXT)
    page.fill("#cmp-b", "My brother thinks it's too slow, and I don't love the price either, to be honest.")
    page.click("#compare-form .primary")
    page.wait_for_selector("#compare-result table", timeout=60000)
    assert "Document score" in page.inner_text("#compare-result table")
    assert page.locator("#compare-result a:has-text('Open the full result')").count() == 2
    assert unexpected(page) == []


def test_batch_scan_lists_rows_and_csv(page, site):
    page.goto(page.url.split("#")[0] + "#/batch")
    page.wait_for_selector("#batch-form")
    items = f"{site}/slop_landing.html\n{site}/plain_article.html\nC:/definitely/missing.md"
    page.fill("#batch-items", items)
    page.click("#batch-form .primary")
    page.wait_for_function(
        "() => { const rows = document.querySelectorAll('#batch-result tbody tr'); return rows.length >= 3; }",
        timeout=120000)
    assert "No such file" in page.inner_text("#batch-result")
    with page.expect_download() as dl:
        page.click("#batch-result a:has-text('CSV')")
    assert dl.value.suggested_filename.endswith(".csv")
    assert unexpected(page) == []


def test_history_lists_and_opens_scan(scanned):
    scanned.goto(scanned.url.split("#")[0] + "#/history")
    scanned.wait_for_selector("#h-on")
    assert scanned.locator("tbody tr.link").count() >= 1
    scanned.click("tbody tr.link")
    scanned.wait_for_selector(".verdict .label", timeout=30000)
    assert unexpected(scanned) == []


def test_history_toggle_and_clear(scanned):
    scanned.goto(scanned.url.split("#")[0] + "#/history")
    scanned.wait_for_selector("#h-on")
    if scanned.is_checked("#h-on"):
        scanned.uncheck("#h-on")
        scanned.wait_for_selector("#h-on")
        assert not scanned.is_checked("#h-on")
    scanned.check("#h-on")
    scanned.wait_for_selector("#h-on")
    scanned.once("dialog", lambda d: d.accept())
    scanned.click("#h-clear")
    page.wait_for_selector(".empty") if False else scanned.wait_for_selector(".empty")
    assert "No scans yet." in scanned.inner_text(".empty")
    assert unexpected(scanned) == []


def test_delete_scan_returns_to_history(scanned):
    scanned.once("dialog", lambda d: d.accept())
    scanned.click("#del")
    scanned.wait_for_function("() => location.hash.endsWith('#/history')", timeout=30000)
    assert unexpected(scanned) == []


def test_models_page_download_flow(page, ctl):
    ctl["fail"] = False
    page.goto(page.url.split("#")[0] + "#/models")
    page.wait_for_selector("h1")
    page.click('button[data-dl="tabularis"]')
    page.wait_for_selector(".state.downloading", timeout=10000)
    row_for(page, "tabularis").locator(".state.ready").first.wait_for(timeout=15000)
    assert "tabularis" in ctl["ready"]
    assert unexpected(page) == []


def test_models_page_failed_download_can_retry(page, ctl):
    ctl["fail"] = True
    page.goto(page.url.split("#")[0] + "#/models")
    page.wait_for_selector("h1")
    page.click('button[data-dl="conpara"]')
    row_for(page, "conpara").locator(".state.failed").first.wait_for(timeout=15000)
    row = row_for(page, "conpara")
    assert row.locator("button:has-text('Retry')").count() >= 1
    ctl["fail"] = False
    row.locator("button:has-text('Retry')").click()
    row_for(page, "conpara").locator(".state.ready").first.wait_for(timeout=15000)
    assert unexpected(page) == []


def test_scan_with_missing_model_downloads_first(page, ctl):
    ctl["fail"] = False
    ctl["ready"].discard("gpttrace-1b")
    page.goto(page.url.split("#")[0] + "#/")
    page.wait_for_selector("#scan-form")
    page.check("#model-picker input[value='gpttrace-1b']")
    page.uncheck("#model-picker input[value='desklib']")
    page.fill("#text", TEXT)
    page.click("#scan-form .primary")
    page.wait_for_function(
        "() => document.querySelector('#scan-progress') && document.querySelector('#scan-progress').innerText.includes('Downloading')",
        timeout=10000)
    page.wait_for_selector(".verdict .label", timeout=60000)
    page.goto(page.url.split("#")[0] + "#/")
    page.wait_for_selector("#scan-form")
    page.check("#model-picker input[value='desklib']")
    page.uncheck("#model-picker input[value='gpttrace-1b']")
    assert unexpected(page) == []


def test_unknown_scan_id_shows_error(page, base_url):
    page.goto(base_url + "/#/scan/doesnotexist")
    page.wait_for_selector(".error", timeout=30000)
    assert unexpected(page) == []


def test_api_rejects_foreign_host(page, base_url):
    resp = page.request.get(base_url + "/api/state", headers={"Host": "evil.example"})
    assert resp.status == 403


def test_narrow_viewport_stacks_layout(scanned):
    scanned.set_viewport_size({"width": 800, "height": 900})
    left_box = scanned.locator("#left").bounding_box()
    side_box = scanned.locator(".side").bounding_box()
    assert side_box["y"] > left_box["y"]
    assert unexpected(scanned) == []
