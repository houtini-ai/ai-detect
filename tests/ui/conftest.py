"""Fixtures for the browser tests of the dashboard.

Skipped as a whole when Playwright (or its Chromium) is not installed. No model
is downloaded or loaded: a fake backend scores sentences by keyword, and the
download manager is driven by ``ctl`` so the download / retry flow can be
exercised in a second.
"""

import functools
import http.server
import os
import threading
import time

import pytest

pytest.importorskip("playwright.sync_api")
from playwright.sync_api import sync_playwright  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
AI_WORDS = ("furthermore", "additionally", "provides", "seamless", "comprehensive")


class FakeBackend:
    device_label = "cpu"

    def __init__(self, name):
        self.name = name

    def margins(self, texts):
        return [6.0 if any(w in t.lower() for w in AI_WORDS) else -6.0 for t in texts]


@pytest.fixture(scope="session")
def ctl():
    """Test control: which models count as downloaded, and whether the next
    simulated download fails."""
    return {"ready": {"desklib", "light", "gpttrace-150m"}, "fail": False}


@pytest.fixture(scope="session")
def base_url(ctl, tmp_path_factory):
    os.environ["AI_DETECT_HOME"] = str(tmp_path_factory.mktemp("home"))
    from ai_detect import analyze, downloads
    from ai_detect.models import REGISTRY
    from ai_detect.web import server

    analyze.get_detector = lambda model, device=None: FakeBackend(REGISTRY.resolve(model).id)
    analyze.unload_detector = lambda model, device=None: True
    downloads.is_model_cached = lambda model: REGISTRY.resolve(model).id in ctl["ready"]

    def fake_download(model, on_progress=None):
        spec = REGISTRY.resolve(model)
        total = spec.approx_mb * 1024 * 1024
        for step in range(1, 6):
            with downloads._LOCK:
                downloads._STATE[spec.id] = {**downloads._blank(spec.id), "state": "downloading",
                                             "started": time.time() - step, "bytes_total": total,
                                             "bytes_done": total * step // 6}
            time.sleep(0.3)
        with downloads._LOCK:
            if ctl["fail"]:
                downloads._STATE[spec.id] = {**downloads._blank(spec.id), "state": "failed",
                                             "error": "ConnectionError: simulated outage"}
            else:
                ctl["ready"].add(spec.id)
                downloads._STATE[spec.id] = {**downloads._blank(spec.id), "state": "ready"}
        return downloads.status(spec.id)

    downloads.download = fake_download
    url = server.ensure_started(port=18765)
    yield url
    server.stop()


@pytest.fixture(scope="session")
def site():
    """A local web server holding the fixture pages, standing in for 'a URL'."""
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=FIXTURES)
    http.server.SimpleHTTPRequestHandler.log_message = lambda *a, **k: None
    httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture(scope="session")
def browser():
    with sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # Chromium not installed
            pytest.skip(f"Chromium is not available: {e}")
        yield b
        b.close()


@pytest.fixture
def page(browser, base_url):
    context = browser.new_context(viewport={"width": 1440, "height": 900}, accept_downloads=True)
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: m.type == "error" and errors.append(m.text))
    page.goto(base_url + "/")
    page.wait_for_selector("#scan-form")
    page.errors = errors
    yield page
    context.close()


AI_TEXT = ("Furthermore, the platform provides a seamless experience for modern teams. "
           "Additionally, it provides comprehensive support across multiple regions. "
           "I don't love the price, though, and my brother thinks it's too slow.")


@pytest.fixture
def scanned(page):
    """A page already showing the result of one text scan."""
    page.fill("#text", AI_TEXT)
    page.click("#scan-form .primary")
    page.wait_for_selector(".verdict .label", timeout=30000)
    return page
