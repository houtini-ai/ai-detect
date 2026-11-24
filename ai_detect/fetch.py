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
* It gives up after ``timeout`` seconds.

Playwright is an optional extra. Without it every function here raises
UrlFetchUnavailable with the two commands that install it.
"""

import os
import re
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


class UrlFetchUnavailable(RuntimeError):
    """Playwright (or its Chromium) is not installed."""


class UrlFetchError(RuntimeError):
    """The page could not be loaded or had no readable content."""


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


def _render(target, timeout, screenshot):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ImportError as e:
        raise UrlFetchUnavailable(INSTALL_HINT) from e

    budget = int(max(1.0, float(timeout)) * 1000)
    try:
        with sync_playwright() as p:
            try:
                browser = p.chromium.launch(headless=True)
            except PlaywrightError as e:
                if "Executable doesn't exist" in str(e) or "playwright install" in str(e):
                    raise UrlFetchUnavailable(INSTALL_HINT) from e
                raise
            try:
                context = browser.new_context(
                    user_agent=_chrome_user_agent(browser), viewport=VIEWPORT,
                    accept_downloads=False, service_workers="block", locale="en-GB",
                )
                context.set_default_timeout(budget)
                page = context.new_page()
                page.on("dialog", lambda d: d.dismiss())
                status = 200
                response = page.goto(target, wait_until="domcontentloaded", timeout=budget)
                status = response.status if response else 0
                try:  # let client-side rendering settle, within the budget
                    page.wait_for_load_state("networkidle", timeout=min(budget, 8000))
                except PlaywrightError:
                    pass
                # One pass down and back so lazy-loaded content is present.
                page.evaluate("async () => { const h = document.documentElement.scrollHeight;"
                              " for (let y = 0; y < h; y += 1200) { window.scrollTo(0, y);"
                              " await new Promise(r => setTimeout(r, 60)); } window.scrollTo(0, 0); }")
                snapshot = page.evaluate(_extract_script())
                shot, clipped = b"", False
                if screenshot:
                    height = snapshot["visual"]["page"]["height"]
                    if height > MAX_SCREENSHOT_HEIGHT:
                        clipped = True
                        page.set_viewport_size({"width": VIEWPORT["width"], "height": 900})
                        shot = page.screenshot(type="jpeg", quality=72, full_page=True, clip={
                            "x": 0, "y": 0, "width": VIEWPORT["width"],
                            "height": MAX_SCREENSHOT_HEIGHT})
                    else:
                        shot = page.screenshot(type="jpeg", quality=72, full_page=True)
                return snapshot, shot, status, page.url, clipped
            finally:
                browser.close()
    except UrlFetchUnavailable:
        raise
    except PlaywrightError as e:
        first = str(e).split("\n")[0]
        if "Timeout" in first:
            raise UrlFetchError(f"Timed out after {timeout:.0f}s loading {target}") from e
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
