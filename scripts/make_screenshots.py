"""Start a dashboard, drive it and save the documentation screenshots.

    python scripts/make_screenshots.py URL

The script starts its own dashboard (this checkout's code) so that nothing
local shows in a picture:

* on the default port, 8765. If that port is busy the script stops: a fallback
  port would appear in every screenshot's footer. Close the other dashboard
  and run it again.
* with AI_DETECT_HOME set to a neutral folder (``C:\\ai-detect-demo`` on
  Windows, ``/srv/ai-detect-demo`` elsewhere; ``--home`` to change it). The
  History page prints that folder, so it must not be a temp path or sit under
  a user's home folder. The folder is removed afterwards if the script made it.

It scans URL twice (the default model alone, then an ensemble with the
perplexity readout), runs one before/after compare on the bundled examples,
and saves a light and a dark screenshot of every view to docs/screenshots/.
Needs Playwright. The screenshots show what the tool reported for that URL on
the day; they are a demonstration of the tool, not a finding about the page.
"""

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "docs", "screenshots")
DEFAULT_PORT = 8765  # ai_detect.web.server.DEFAULT_PORT; checked against it in main()
BASE = f"http://127.0.0.1:{DEFAULT_PORT}"
# The default model first, then the other four of the worked example.
ENSEMBLE = ["gpttrace-150m", "desklib", "gpttrace-1b", "tabularis", "light"]
_PRIVATE_PARTS = {"users", "home", "temp", "tmp", "appdata", "documents", "desktop"}


def neutral_home():
    """A folder whose path says nothing about this machine or its user."""
    if os.name == "nt":
        drive = os.environ.get("SystemDrive") or "C:"
        return drive + "\\ai-detect-demo"
    return "/srv/ai-detect-demo"


def shows_something_local(path):
    """Would this path, printed on the History page, show a user name, a home
    folder or a temp folder?"""
    full = os.path.normcase(os.path.abspath(path))
    for private in (os.path.expanduser("~"), tempfile.gettempdir()):
        private = os.path.normcase(os.path.abspath(private))
        if full == private or full.startswith(private.rstrip("\\/") + os.sep):
            return True
    parts = {p.lower() for p in full.replace("\\", "/").split("/") if p}
    return bool(parts & _PRIVATE_PARTS)


def engine_env(home):
    """The environment the dashboard is started in: the neutral home, the
    default port, and nothing inherited that would move either."""
    env = dict(os.environ)
    env["AI_DETECT_HOME"] = home
    env["AI_DETECT_PORT"] = str(DEFAULT_PORT)
    env["AI_DETECT_HISTORY"] = "on"
    env["PYTHONPATH"] = ROOT + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    return env


def port_is_free(port=DEFAULT_PORT):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def start_engine(home):
    """Start this checkout's dashboard on the default port. Returns the process."""
    if not port_is_free():
        sys.exit(f"Port {DEFAULT_PORT} is in use. Stop whatever is listening there (another "
                 "ai-detect dashboard?) and run this again: a fallback port would show in "
                 "every screenshot.")
    process = subprocess.Popen(
        [sys.executable, "-m", "ai_detect.cli", "serve", "--no-browser", "--port", str(DEFAULT_PORT)],
        cwd=ROOT, env=engine_env(home), stdin=subprocess.DEVNULL)
    deadline = time.time() + 90
    while time.time() < deadline:
        if process.poll() is not None:
            sys.exit(f"The dashboard exited with code {process.returncode} before it answered.")
        try:
            state = call(BASE, "/api/state")
        except (OSError, ValueError):
            time.sleep(0.5)
            continue
        if os.path.normcase(state["history"]["folder"]).startswith(os.path.normcase(home)):
            return process
        process.terminate()
        sys.exit(f"Something else answered on {BASE}; its history folder is "
                 f"{state['history']['folder']}.")
    process.terminate()
    sys.exit("The dashboard did not answer within 90 seconds.")


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
            raise RuntimeError(f"{kind} failed: {j['error']}")
        print("  ", j["progress"].get("stage"), j["progress"].get("model", ""), flush=True)
        time.sleep(4)


def capture(url):
    from playwright.sync_api import sync_playwright

    default_model = call(BASE, "/api/state")["default_model"]
    os.makedirs(OUT, exist_ok=True)
    print("single-model scan:", default_model)
    single = job(BASE, "scan", {"url": url, "models": [default_model]})["scan_id"]
    print("ensemble scan")
    multi = job(BASE, "scan", {"url": url, "models": ENSEMBLE, "perplexity": True})["scan_id"]

    def read(name):
        with open(os.path.join(ROOT, "examples", name), encoding="utf-8") as f:
            return f.read()

    print("compare")
    any_sentence = "span.s.h4, span.s.h3, span.s.h2, span.s.h1, span.s.h0"
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
                page.goto(BASE + "/" + hash_)
                page.wait_for_selector(selector, timeout=30000)

            go("#/", "#scan-form"); page.click('[role=tab][data-src="url"]'); page.fill("#url", url)
            shot("scan-form")
            go(f"#/scan/{single}", ".verdict .label"); page.locator(any_sentence).first.click()
            shot("result-single-model")
            go(f"#/scan/{multi}", ".verdict .label"); page.locator(any_sentence).first.click()
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
                html = urllib.request.urlopen(f"{BASE}/api/scans/{multi}/export.html").read().decode()
                page.set_content(html); shot("export-html-report")
            ctx.close()
        browser.close()
    print(json.dumps({"single": single, "ensemble": multi, "default_model": default_model}))


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("url")
    ap.add_argument("--home", default=neutral_home(),
                    help="AI_DETECT_HOME for the dashboard (shown on the History page)")
    args = ap.parse_args()
    sys.path.insert(0, ROOT)
    from ai_detect.web.server import DEFAULT_PORT as real_default
    if real_default != DEFAULT_PORT:
        sys.exit(f"The dashboard's default port is now {real_default}; update DEFAULT_PORT here.")
    home = os.path.abspath(args.home)
    if shows_something_local(home):
        sys.exit(f"{home} would show a user or temp folder in the History screenshot. "
                 "Pick a neutral --home.")
    made = not os.path.exists(home)
    os.makedirs(home, exist_ok=True)
    engine = start_engine(home)
    try:
        capture(args.url)
    finally:
        engine.terminate()
        try:
            engine.wait(timeout=10)
        except subprocess.TimeoutExpired:
            engine.kill()
        if made:
            shutil.rmtree(home, ignore_errors=True)


if __name__ == "__main__":
    main()
