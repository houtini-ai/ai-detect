"""Fetch one web page with headless Chromium and parse its article content.

Why a browser: plain HTTP fetches are refused by many sites and return an
unrendered shell on others. Playwright's Chromium renders the page the way a
reader sees it; a script then reads the article structure and layout out of
the live DOM (ai_detect/assets/extract.js).

What it will and will not do:

* It loads exactly the URL it was given. It follows that URL's own redirects
  and loads the page's own sub-resources, and nothing else: no crawling.
* It never clicks, types, submits a form or signs in. Downloads are refused.
* The only data that leaves the machine is the request for the page itself.
* It gives up after ``timeout`` seconds: one deadline, started when the browser
  is up, covers navigation, settling, scrolling, extraction and the screenshot
  together. Starting Chromium itself is not counted against it.
* It only talks to public internet addresses. A URL whose host is, or resolves
  to, a loopback, private (RFC 1918 / unique-local), link-local, carrier-grade
  NAT, multicast, unspecified or reserved address is refused before a browser
  starts, and the same rule is applied inside the browser to every request the
  page makes, redirect hops included, so a public page cannot bounce the fetch
  to this machine, the local network or a cloud metadata service. Set
  ``AI_DETECT_ALLOW_PRIVATE_URLS=1`` to turn the rule off (to scan a site on
  your own machine or LAN). Rendering a local .html file is not affected, but
  the rule still applies to what that file loads.

  Limits of the rule, stated plainly: the address check and the browser's own
  connection each resolve the name, so a DNS answer that changes between the
  two (DNS rebinding) is not caught; a name that does not resolve here is left
  for the browser to fail on; WebSocket connections are not inspected.

Playwright is an optional extra. Without it every function here raises
UrlFetchUnavailable with the two commands that install it.
"""

import ipaddress
import os
import re
import socket
import time
from dataclasses import dataclass, field
from importlib import resources
from urllib.parse import urlparse

from .text import Block, Document

DEFAULT_TIMEOUT = 30.0
VIEWPORT = {"width": 1366, "height": 900}
MAX_SCREENSHOT_HEIGHT = 16000  # px; taller pages are clipped (and say so)

INSTALL_HINT = (
    "URL input needs Playwright and its Chromium build, which are not installed.\n"
    "From the ai-detect folder run:\n"
    '    pip install ".[web]"\n'
    "    playwright install chromium"
)


DEPS_HINT = (
    "If both are installed and the browser still cannot start, the system is missing "
    "libraries it needs. On Debian or Ubuntu run (as root, or with sudo):\n"
    "    playwright install --with-deps chromium"
)

# What Playwright says when Chromium or its driver cannot start at all, as
# against a page that would not load.
_NOT_INSTALLED = ("Executable doesn't exist", "playwright install")
_MISSING_LIBRARIES = (
    "missing dependencies", "error while loading shared libraries",
    "cannot open shared object file", "Failed to launch",
)


class UrlFetchUnavailable(RuntimeError):
    """Playwright (or its Chromium) is not installed, or cannot start."""


def _cannot_start(error):
    """The install message, plus the line of ``error`` that says what failed."""
    frame = set("\u2550\u2554\u2557\u255a\u255d\u2551+-=| \t")
    lines = [ln.strip("\u2551| \t") for ln in str(error).splitlines() if set(ln) - frame]
    first = lines[0] if lines else type(error).__name__
    telling = next((ln for ln in lines if any(m in ln for m in _MISSING_LIBRARIES)), first)
    if telling != first and first.startswith("BrowserType.launch"):
        telling = f"{first.rstrip(':')}: {telling}" if len(first) < 30 else telling
    return UrlFetchUnavailable(
        f"{INSTALL_HINT}\n{DEPS_HINT}\nThe underlying error was: "
        f"{type(error).__name__}: {telling[:400]}")


class UrlFetchError(RuntimeError):
    """The page could not be loaded or had no readable content."""


class PrivateAddressError(UrlFetchError):
    """The URL (or a redirect from it) points at a non-public address."""


# ---------------------------------------------------------------------------
# Public addresses only
# ---------------------------------------------------------------------------

ALLOW_PRIVATE_ENV = "AI_DETECT_ALLOW_PRIVATE_URLS"
_NETWORK_SCHEMES = ("http", "https", "ws", "wss")
_NAT64 = ipaddress.ip_network("64:ff9b::/96")
_CGNAT = ipaddress.ip_network("100.64.0.0/10")


def private_urls_allowed():
    """True when the user has opted in to fetching non-public addresses."""
    return os.environ.get(ALLOW_PRIVATE_ENV, "").strip().lower() in ("1", "true", "yes", "on")


def _address_kind(address):
    """'' for a public address, else what kind of non-public address it is."""
    try:
        ip = ipaddress.ip_address(address.split("%", 1)[0])
    except ValueError:
        return "an unreadable address"
    if ip.version == 6:  # judge an IPv4 address carried inside an IPv6 one by the IPv4 rules
        inner = ip.ipv4_mapped or ip.sixtofour
        if inner is None and ip in _NAT64:
            inner = ipaddress.ip_address(int(ip) & 0xFFFFFFFF)
        if inner is not None:
            return _address_kind(str(inner))
    if ip.is_loopback:
        return "a loopback address (this machine)"
    if ip.is_unspecified:
        return "the unspecified address"
    if ip.is_link_local:
        return "a link-local address"
    if ip.is_multicast:
        return "a multicast address"
    if ip.version == 4 and ip in _CGNAT:
        return "a carrier-grade NAT (shared) address"
    if ip.is_private:
        return "a private-network address"
    if ip.is_reserved or not ip.is_global:
        return "a reserved address"
    return ""


def blocked_reason(url, resolve=None):
    """Why this URL must not be fetched, or '' if it may be.

    Only http(s) and ws(s) URLs are judged; file:, data:, blob: and about: never
    leave the machine. The host is refused when it is a non-public IP literal,
    is ``localhost`` (or ends in ``.localhost``), or is a name with at least one
    non-public address. ``resolve`` stands in for socket.getaddrinfo in tests.
    Ignores the AI_DETECT_ALLOW_PRIVATE_URLS switch: callers check that.
    """
    try:
        parts = urlparse((url or "").strip())
        host = (parts.hostname or "").rstrip(".").lower()
    except ValueError:
        return "its address could not be read"
    if parts.scheme.lower() not in _NETWORK_SCHEMES:
        return ""
    if not host:
        return "it has no host"
    if host == "localhost" or host.endswith(".localhost"):
        return f"{host} is a loopback address (this machine)"
    try:
        ipaddress.ip_address(host.split("%", 1)[0])
        literal = True
    except ValueError:
        literal = False
    if literal:
        kind = _address_kind(host)
        return f"{host} is {kind}" if kind else ""
    try:
        found = (resolve or socket.getaddrinfo)(host, None, type=socket.SOCK_STREAM)
    except (OSError, UnicodeError):
        return ""  # does not resolve here: the browser will report that itself
    for entry in found:
        address = str(entry[4][0])
        kind = _address_kind(address)
        if kind:
            return f"{host} resolves to {address}, {kind}"
    return ""


def _refusal(url, reason, via=""):
    hop = f" (reached from {via})" if via and via != url else ""
    return PrivateAddressError(
        f"Refused to fetch {url}{hop}: {reason}. ai-detect only fetches public internet "
        "addresses, so a page cannot be used to reach this machine or the local network. "
        f"To scan a site on your own machine or LAN, set {ALLOW_PRIVATE_ENV}=1 in the "
        "environment ai-detect runs in and start it again.")


def check_public_url(url, resolve=None):
    """Raise PrivateAddressError unless the URL's host is a public address (or
    the user has set AI_DETECT_ALLOW_PRIVATE_URLS=1)."""
    if private_urls_allowed():
        return
    reason = blocked_reason(url, resolve)
    if reason:
        raise _refusal(url, reason)


class _Guard:
    """The same rule, applied to every request a rendered page makes.

    Two hooks are needed because Playwright's ``context.route`` is not called
    for redirect hops (checked against Playwright 1.58: a 302 from a public
    page to 127.0.0.1 was followed without the route handler seeing it):

    * ``context.route`` sees the first request of every navigation and
      sub-resource in the context;
    * a Chrome DevTools ``Fetch`` session on the page sees every hop of every
      request that page makes, including the redirected ones.

    The fetcher has one page: Chromium is started with
    ``--block-new-web-contents``, so a page cannot open a second window that
    would have no redirect check of its own. ``close_popups`` is the backstop.
    """

    def __init__(self, resolve=None):
        self._resolve = resolve
        self._hosts = {}     # host -> reason ('' = allowed), so each name is resolved once
        self.refused = []    # [(url, reason)]

    def allows(self, url):
        try:
            parts = urlparse(url)
            key = (parts.scheme.lower() in _NETWORK_SCHEMES, (parts.hostname or "").lower())
        except ValueError:
            key = (True, url)
        if key not in self._hosts:
            self._hosts[key] = blocked_reason(url, self._resolve)
        reason = self._hosts[key]
        if reason:
            self.refused.append((url, reason))
        return not reason

    def install(self, context, error_type):
        def on_route(route):
            try:
                if self.allows(route.request.url):
                    route.continue_()
                else:
                    route.abort("blockedbyclient")
            except error_type:
                pass  # the request or its page has already gone

        context.route("**/*", on_route)

    def watch(self, context, page, error_type):
        """Attach the redirect-hop check to the page. Call it after new_page()
        has returned, not from the context's "page" event: a CDP session opened
        inside that event stalls new_page() for seconds and attaches too late."""
        session = context.new_cdp_session(page)

        def on_paused(event):
            try:
                if self.allows(event["request"]["url"]):
                    session.send("Fetch.continueRequest", {"requestId": event["requestId"]})
                else:
                    session.send("Fetch.failRequest", {"requestId": event["requestId"],
                                                       "errorReason": "BlockedByClient"})
            except error_type:
                pass

        session.on("Fetch.requestPaused", on_paused)
        session.send("Fetch.enable", {"patterns": [{"urlPattern": "*"}]})

    @staticmethod
    def close_popups(context, error_type):
        def on_page(popup):
            try:
                popup.close()
            except error_type:
                pass

        context.on("page", on_page)


class _Deadline:
    """One time budget for a whole fetch. ``ms()`` is the time left, for the
    next step's own timeout; when none is left it raises the timeout error."""

    def __init__(self, seconds, target, clock=time.monotonic):
        self.seconds = max(1.0, float(seconds))
        self.target = target
        self._clock = clock
        self._end = clock() + self.seconds

    def ms(self, cap=None):
        left = int((self._end - self._clock()) * 1000)
        if left <= 0:
            raise _timed_out(self.seconds, self.target)
        return min(left, cap) if cap else left


def _timed_out(seconds, target):
    return UrlFetchError(f"Timed out after {max(1.0, float(seconds)):.0f}s loading {target}")


@dataclass
class FetchResult:
    document: Document
    visual: dict = field(default_factory=dict)
    screenshot: bytes = b""        # JPEG of the full page, or empty
    url: str = ""                  # final URL after redirects
    status: int = 0
    clipped: bool = False          # screenshot shorter than the page


def is_url(value):
    """True for an http(s) URL with a host. Anything else is text or a path."""
    if not isinstance(value, str) or " " in value.strip() or "\n" in value:
        return False
    parts = urlparse(value.strip())
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _check_url(url):
    url = (url or "").strip()
    parts = urlparse(url)
    if parts.scheme not in ("http", "https") or not parts.netloc:
        raise ValueError(f"Not a fetchable URL (need http:// or https://): {url!r}")
    return url


def _extract_script():
    return resources.files("ai_detect").joinpath("assets/extract.js").read_text(encoding="utf-8")


def document_from_snapshot(snapshot, source="url"):
    """Build a Document from the dict extract.js returns."""
    blocks = [
        Block(b["kind"], b["text"], int(b.get("level") or 0), dict(b.get("meta") or {}))
        for b in snapshot.get("blocks", [])
        if b.get("text")
    ]
    meta = {k: snapshot.get(k) for k in ("url", "lang", "generator", "description", "root")
            if snapshot.get(k)}
    return Document(blocks=blocks, title=snapshot.get("title", ""), source=source, meta=meta)


def _chrome_user_agent(browser):
    """A current desktop Chrome user agent matching the Chromium actually running
    (headless Chromium otherwise announces itself as HeadlessChrome)."""
    major = (browser.version or "140").split(".")[0]
    return ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            f"(KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36")


_SCROLL_SCRIPT = ("async () => { const h = document.documentElement.scrollHeight;"
                  " for (let y = 0; y < h; y += 1200) { window.scrollTo(0, y);"
                  " await new Promise(r => setTimeout(r, 60)); } window.scrollTo(0, 0); }")


def _evaluate(page, function_source, deadline, error_type):
    """Run a JavaScript function in the page and return its (JSON) result, within
    the deadline. ``page.evaluate`` takes no timeout and waits for ever on a page
    that never yields; ``wait_for_function`` is timed by Playwright itself, so it
    is used here to call the function once and hand back what it returned.

    Playwright 1.58 runs this on a page whose Content-Security-Policy forbids
    eval (tests/ui/test_fetch_guard.py). Should a Playwright build refuse it
    there, the function is run with the untimed ``page.evaluate`` instead."""
    wrapped = "async () => { const value = await (" + function_source + ")(); return { value }; }"
    try:
        handle = page.wait_for_function(wrapped, timeout=deadline.ms())
    except error_type as e:
        if any(mark in str(e) for mark in ("EvalError", "unsafe-eval", "Content Security Policy")):
            return page.evaluate(function_source)
        raise
    try:
        return handle.json_value()["value"]
    finally:
        handle.dispose()


def _render(target, timeout, screenshot):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise UrlFetchUnavailable(INSTALL_HINT) from e

    guard = None if private_urls_allowed() else _Guard()
    try:
        manager = sync_playwright()
        try:
            # Starts Playwright's driver (a bundled Node). On a system without
            # the libraries it needs this fails with a plain Exception or an
            # OSError, not a PlaywrightError.
            p = manager.__enter__()
        except Exception as e:
            raise _cannot_start(e) from e
        try:
            try:
                # The fetcher has one page. This Chromium switch makes window.open
                # and every other script-opened window fail, so there is never a
                # second page outside the request guard below.
                browser = p.chromium.launch(headless=True, args=["--block-new-web-contents"])
            except PlaywrightError as e:
                if any(mark in str(e) for mark in _NOT_INSTALLED + _MISSING_LIBRARIES):
                    raise _cannot_start(e) from e
                raise
            try:
                context = browser.new_context(
                    user_agent=_chrome_user_agent(browser), viewport=VIEWPORT,
                    accept_downloads=False, service_workers="block", locale="en-GB",
                )
                context.set_default_timeout(int(max(1.0, float(timeout)) * 1000))
                if guard:
                    guard.install(context, PlaywrightError)
                page = context.new_page()
                if guard:
                    guard.watch(context, page, PlaywrightError)
                    guard.close_popups(context, PlaywrightError)
                page.on("dialog", lambda d: d.dismiss())
                # One deadline from here on: every step gets the time that is left.
                deadline = _Deadline(timeout, target)
                response = page.goto(target, wait_until="domcontentloaded", timeout=deadline.ms())
                status = response.status if response else 0
                try:  # let client-side rendering settle, within the budget
                    page.wait_for_load_state("networkidle", timeout=deadline.ms(cap=8000))
                except PlaywrightError:
                    pass
                # One pass down and back so lazy-loaded content is present.
                _evaluate(page, _SCROLL_SCRIPT, deadline, PlaywrightError)
                snapshot = _evaluate(page, _extract_script(), deadline, PlaywrightError)
                shot, clipped = b"", False
                if screenshot:
                    height = snapshot["visual"]["page"]["height"]
                    if height > MAX_SCREENSHOT_HEIGHT:
                        clipped = True
                        page.set_viewport_size({"width": VIEWPORT["width"], "height": 900})
                        shot = page.screenshot(type="jpeg", quality=72, full_page=True, clip={
                            "x": 0, "y": 0, "width": VIEWPORT["width"],
                            "height": MAX_SCREENSHOT_HEIGHT}, timeout=deadline.ms())
                    else:
                        shot = page.screenshot(type="jpeg", quality=72, full_page=True,
                                               timeout=deadline.ms())
                return snapshot, shot, status, page.url, clipped
            finally:
                browser.close()
        finally:
            try:
                manager.__exit__(None, None, None)
            except Exception:
                pass  # the driver has already gone
    except UrlFetchUnavailable:
        raise
    except PlaywrightError as e:
        first = str(e).split("\n")[0]
        if guard and guard.refused and "ERR_BLOCKED_BY_CLIENT" in first:
            url, reason = guard.refused[0]
            raise _refusal(url, reason, via=target) from e
        if "Timeout" in first:
            raise _timed_out(timeout, target) from e
        raise UrlFetchError(f"Could not load {target}: {first}") from e


def _result(snapshot, shot, status, final_url, clipped, source):
    document = document_from_snapshot(snapshot, source=source)
    if not any(b.kind in ("paragraph", "list_item", "quote") for b in document.blocks):
        raise UrlFetchError(
            f"No readable article text found at {final_url} (HTTP {status}). The page may "
            "need a sign-in, block automated browsers, or hold no prose.")
    visual = dict(snapshot.get("visual") or {})
    visual["clipped_at"] = MAX_SCREENSHOT_HEIGHT if clipped else None
    return FetchResult(document=document, visual=visual, screenshot=shot, url=final_url,
                       status=status, clipped=clipped)


def fetch_url(url, timeout=DEFAULT_TIMEOUT, screenshot=True):
    """Render one http(s) URL and return its parsed article, layout snapshot and
    a full-page screenshot."""
    url = _check_url(url)
    check_public_url(url)
    snapshot, shot, status, final_url, clipped = _render(url, timeout, screenshot)
    if status >= 400:
        raise UrlFetchError(f"{url} answered HTTP {status}")
    return _result(snapshot, shot, status, final_url, clipped, "url")


def fetch_html_file(path, timeout=DEFAULT_TIMEOUT, screenshot=True):
    """Render a local .html file the same way (used for saved pages and tests)."""
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise FileNotFoundError(f"No such file: {path}")
    from pathlib import Path
    snapshot, shot, status, _final, clipped = _render(Path(path).as_uri(), timeout, screenshot)
    return _result(snapshot, shot, status, path, clipped, "file")


_HTML_RX = re.compile(r"<\s*(?:!doctype\s+html|html|body|article|p|div)\b", re.IGNORECASE)


def looks_like_html(text):
    return bool(_HTML_RX.search(text[:2000]))
