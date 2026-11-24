"""Browser tests for the fetcher's public-address rule and its single deadline.

Real Chromium, no internet. Two loopback addresses stand in for the two sides:
127.0.0.2 plays "a public site" (the address rule is told to accept it) and
127.0.0.1 plays "something on this machine" that must never be requested.
"""

import http.server
import os
import socketserver
import threading
import time

import pytest

from ai_detect import fetch

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures")
PROSE = "<p>" + "This is an ordinary paragraph of prose for the article. " * 6 + "</p>"


def _off_thread(function, *args, **kwargs):
    """Run a fetch on its own thread, as the dashboard's job worker does. The
    dashboard tests in this folder keep a Playwright browser open on the test
    thread, and Playwright's sync API cannot be started twice on one thread."""
    box = {}

    def run():
        try:
            box["value"] = function(*args, **kwargs)
        except BaseException as e:
            box["error"] = e

    thread = threading.Thread(target=run)
    thread.start()
    thread.join(timeout=120)
    assert not thread.is_alive(), "the fetch did not return"
    if "error" in box:
        raise box["error"]
    return box["value"]


def _fetch_url(*args, **kwargs):
    return _off_thread(fetch.fetch_url, *args, **kwargs)


def _fetch_html_file(*args, **kwargs):
    return _off_thread(fetch.fetch_html_file, *args, **kwargs)


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True

    def server_bind(self):  # skip HTTPServer's reverse DNS lookup of the address (seconds)
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address[:2]


def _serve(host, handler):
    try:
        httpd = _Server((host, 0), handler)
    except OSError as e:
        pytest.skip(f"cannot listen on {host}: {e}")
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    return httpd


class _Quiet(http.server.BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def page(self, body, status=200, csp=""):
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        if csp:
            self.send_header("Content-Security-Policy", csp)
        self.end_headers()
        self.wfile.write(("<html><body><article>" + body + "</article></body></html>").encode())


@pytest.fixture
def inside():
    """The thing that must not be reached: records every request it gets."""
    hits = []

    class Handler(_Quiet):
        def do_GET(self):
            hits.append(self.path)
            self.page("<h1>Internal</h1>" + PROSE)

    httpd = _serve("127.0.0.1", Handler)
    yield {"url": f"http://127.0.0.1:{httpd.server_address[1]}", "hits": hits}
    httpd.shutdown()


@pytest.fixture
def outside(inside, monkeypatch):
    """The 'public' site on 127.0.0.2. Its paths:
    /redirect  302 to the inside server
    /hop       302 to /redirect (two hops)
    /page      an article that embeds the inside server directly and by redirect
    /popup     an article that opens /redirect in a new window
    /csp       an article whose Content-Security-Policy forbids eval and inline script
    /tall      a very tall article (slow to scroll)
    /slow      answers after twenty seconds
    """
    class Handler(_Quiet):
        def do_GET(self):
            if self.path.startswith("/redirect"):
                self.send_response(302)
                self.send_header("Location", inside["url"] + "/secret")
                self.end_headers()
            elif self.path.startswith("/hop"):
                self.send_response(302)
                self.send_header("Location", "/redirect")
                self.end_headers()
            elif self.path.startswith("/page"):
                self.page("<h1>Outside</h1>" + PROSE + f'<img src="{inside["url"]}/direct.png">'
                          '<img src="/redirect?img"><iframe src="/redirect?frame"></iframe>'
                          f'<script>fetch("{inside["url"]}/xhr").catch(() => 0)</script>')
            elif self.path.startswith("/popup"):
                self.page("<h1>Outside</h1>" + PROSE
                          + '<script>window.open("/redirect?popup")</script>')
            elif self.path.startswith("/csp"):
                self.page("<h1>Strict</h1>" + PROSE, csp="default-src 'self'; script-src 'self'")
            elif self.path.startswith("/tall"):
                self.page("<h1>Tall</h1>" + PROSE + '<div style="height:400000px"></div>')
            elif self.path.startswith("/slow"):
                time.sleep(20)
                self.page(PROSE)
            else:
                self.page("<h1>Outside</h1>" + PROSE)

    httpd = _serve("127.0.0.2", Handler)
    real = fetch._address_kind
    monkeypatch.setattr(fetch, "_address_kind", lambda a: "" if a == "127.0.0.2" else real(a))
    yield f"http://127.0.0.2:{httpd.server_address[1]}"
    httpd.shutdown()


@pytest.fixture
def guarded(monkeypatch):
    monkeypatch.delenv(fetch.ALLOW_PRIVATE_ENV, raising=False)


def test_public_page_renders_with_the_rule_on(guarded, outside):
    result = _fetch_url(outside + "/plain", timeout=30, screenshot=False)
    assert result.status == 200
    assert any("ordinary paragraph" in b.text for b in result.document.blocks)


def test_a_page_with_a_strict_content_security_policy_is_still_read(guarded, outside):
    result = _fetch_url(outside + "/csp", timeout=30, screenshot=True)
    assert any("ordinary paragraph" in b.text for b in result.document.blocks)
    assert result.screenshot


def test_redirect_to_a_private_address_is_refused_and_never_requested(guarded, outside, inside):
    with pytest.raises(fetch.PrivateAddressError) as e:
        _fetch_url(outside + "/redirect", timeout=30, screenshot=False)
    message = str(e.value)
    assert inside["url"] + "/secret" in message and "loopback" in message
    assert outside + "/redirect" in message and fetch.ALLOW_PRIVATE_ENV in message
    assert inside["hits"] == []


def test_a_second_redirect_hop_is_refused_too(guarded, outside, inside):
    with pytest.raises(fetch.PrivateAddressError):
        _fetch_url(outside + "/hop", timeout=30, screenshot=False)
    assert inside["hits"] == []


def test_sub_resources_cannot_reach_a_private_address(guarded, outside, inside):
    result = _fetch_url(outside + "/page", timeout=30, screenshot=False)
    assert any("ordinary paragraph" in b.text for b in result.document.blocks)
    assert inside["hits"] == []


def test_a_window_opened_by_the_page_cannot_reach_a_private_address(guarded, outside, inside):
    result = _fetch_url(outside + "/popup", timeout=30, screenshot=False)
    assert any("ordinary paragraph" in b.text for b in result.document.blocks)
    assert inside["hits"] == []


def test_the_env_switch_lets_the_redirect_through(monkeypatch, outside, inside):
    monkeypatch.setenv(fetch.ALLOW_PRIVATE_ENV, "1")
    result = _fetch_url(outside + "/redirect", timeout=30, screenshot=False)
    assert result.url == inside["url"] + "/secret"
    assert inside["hits"] == ["/secret"]


def test_local_html_file_still_renders_with_the_rule_on(guarded):
    result = _fetch_html_file(os.path.join(FIXTURES, "plain_article.html"), timeout=30)
    assert result.document.blocks and result.screenshot


def test_local_html_file_cannot_load_from_a_private_address(guarded, inside, tmp_path):
    page = tmp_path / "saved.html"
    page.write_text("<html><body><article>" + PROSE + f'<img src="{inside["url"]}/x.png">'
                    "</article></body></html>", encoding="utf-8")
    result = _fetch_html_file(str(page), timeout=30, screenshot=False)
    assert result.document.blocks
    assert inside["hits"] == []


def test_a_slow_server_times_out_at_the_deadline(guarded, outside):
    started = time.time()
    with pytest.raises(fetch.UrlFetchError) as e:
        _fetch_url(outside + "/slow", timeout=2, screenshot=False)
    assert "Timed out after 2s" in str(e.value)
    assert time.time() - started < 15  # the 2s, plus starting and closing Chromium


def test_the_deadline_covers_the_steps_after_navigation(guarded, outside):
    # Navigation is instant; scrolling this page takes about 20 seconds. The
    # whole fetch is given 4, so the scroll step must be cut short.
    started = time.time()
    with pytest.raises(fetch.UrlFetchError) as e:
        _fetch_url(outside + "/tall", timeout=4, screenshot=True)
    assert "Timed out after 4s" in str(e.value)
    assert time.time() - started < 15  # the 4s, plus starting and closing Chromium
