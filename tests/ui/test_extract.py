"""The page extractor on an article whose own class name holds a noise word.

Found on 25 Nov 2026: a Substack post is ``<article class="typography
newsletter-post post">``. "newsletter" is in the extractor's noise list, so the
whole article was skipped and the scan ended with "No readable article text".
The article also sits inside a ``display: contents`` wrapper, which has an
empty rectangle and was taken for an invisible element.
"""

import os
import threading

from ai_detect import fetch

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "fixtures", "newsletter-article.html")


def _read():
    """Fetch on a thread of its own: the session's browser fixture already runs
    Playwright's sync API on the test thread, and it cannot be started twice."""
    box = {}
    thread = threading.Thread(target=lambda: box.update(result=fetch.fetch_html_file(FIXTURE, screenshot=False)))
    thread.start()
    thread.join(timeout=120)
    return box["result"]


def test_article_named_newsletter_post_is_read(browser):
    result = _read()
    kinds = [b.kind for b in result.document.blocks]
    text = " ".join(b.text for b in result.document.blocks)
    assert kinds.count("paragraph") == 3 and kinds.count("list_item") == 2
    assert "fitted backwards in 1987" in text and "under the passenger seat" in text
    assert "What the plumber said" in text


def test_noise_inside_that_article_is_still_dropped(browser):
    result = _read()
    text = " ".join(b.text for b in result.document.blocks)
    assert "Type your email" not in text        # the sign-up box inside the article
    assert "Not part of the body" not in text   # the post header
    assert "Footer text" not in text
