"""Drive a running dashboard and save the documentation screenshots.

    ai-detect serve --no-browser            # in another terminal
    python scripts/make_screenshots.py URL [--base http://127.0.0.1:8765]

Scans URL twice (the default model alone, then an ensemble with the perplexity
readout), runs one before/after compare on the bundled examples, and saves a
light and a dark screenshot of every view to docs/screenshots/. Needs
Playwright. The screenshots show what the tool reported for that URL on the day;
they are a demonstration of the tool, not a finding about the page.
"""

import argparse
import json
import os
import sys
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "screenshots")
ENSEMBLE = ["desklib", "gpttrace-150m", "gpttrace-1b", "tabularis", "light"]


def call(base, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def job(base, kind, body):
    job_id = call(base, f"/api/start/{kind}", body)["job_id"]
    while True:
        j = call(base, f"/api/jobs/{job_id}")
        if j["state"] == "done":
            return j["result"]
        if j["state"] == "failed":
            sys.exit(f"{kind} failed: {j['error']}")
        print("  ", j["progress"].get("stage"), j["progress"].get("model", ""), flush=True)
        time.sleep(4)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("url")
    ap.add_argument("--base", default="http://127.0.0.1:8765")
    args = ap.parse_args()
    from playwright.sync_api import sync_playwright

    os.makedirs(OUT, exist_ok=True)
    print("single-model scan"); single = job(args.base, "scan", {"url": args.url, "models": ["desklib"]})["scan_id"]
    print("ensemble scan"); multi = job(args.base, "scan", {"url": args.url, "models": ENSEMBLE, "perplexity": True})["scan_id"]
    read = lambda name: open(os.path.join(ROOT, "examples", name), encoding="utf-8").read()
    print("compare")
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for theme in ("dark", "light"):
            ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, device_scale_factor=1)
            ctx.add_init_script(f"localStorage.setItem('ai-detect-theme', '{theme}');"
                                f"localStorage.setItem('ai-detect-models', '{json.dumps(ENSEMBLE)}')")
            page = ctx.new_page()

            def shot(name, full=False):
                page.wait_for_timeout(500)
                page.screenshot(path=os.path.join(OUT, f"{name}-{theme}.png"), full_page=full)
                print("saved", f"{name}-{theme}.png")

            def go(hash_, selector):
                page.goto(args.base + "/" + hash_)
                page.wait_for_selector(selector, timeout=30000)

            go("#/", "#scan-form"); page.click('[role=tab][data-src="url"]'); page.fill("#url", args.url)
            shot("scan-form")
            go(f"#/scan/{single}", ".verdict .label"); page.click("span.s.h4, span.s.h3, span.s.h2")
            shot("result-single-model")
            go(f"#/scan/{multi}", ".verdict .label"); page.click("span.s.h4, span.s.h3, span.s.h2")
            shot("result-ensemble")
            page.click('#view button[data-v="table"]'); shot("ensemble-sentences-table")
            page.click('#view button[data-v="text"]'); page.click('.side [data-p="tells"]')
            if page.locator(".card[data-t]").count():
                page.click(".card[data-t] >> nth=0")
            shot("tells-panel")
            page.click('.side [data-p="rewrite"]'); shot("rewrite-panel")
            page.click('.side [data-p="models"]'); shot("models-panel")
            page.click('.side [data-p="signals"]'); shot("signals-perplexity")
            if page.locator('#view button[data-v="page"]').count():
                page.click('#view button[data-v="page"]')
                page.wait_for_function("() => { const i = document.querySelector('#shot img'); return i && i.complete; }")
                page.click('.side [data-p="tells"]')
                visual = page.locator(".box.visual")
                if visual.count():
                    visual.first.click()
                elif page.locator(".card[data-t]").count():
                    page.click(".card[data-t] >> nth=0")
                shot("page-view-annotated")
            go("#/compare", "#compare-form")
            page.fill("#cmp-a", read("ai-sample.txt")); page.fill("#cmp-b", read("human-sample.txt"))
            page.click("#compare-form .primary"); page.wait_for_selector("#compare-result table", timeout=600000)
            shot("compare", full=True)
            go("#/models", "table"); shot("models", full=True)
            go("#/history", "h1"); shot("history")
            if theme == "light":
                html = urllib.request.urlopen(f"{args.base}/api/scans/{multi}/export.html").read().decode()
                page.set_content(html); shot("export-html-report")
            ctx.close()
        browser.close()
    print(json.dumps({"single": single, "ensemble": multi}))


if __name__ == "__main__":
    main()
