"""Fixes found while documenting 2.0.0 (25 Nov 2026)."""

import importlib.util
import os
import sys
import tempfile
import types

import pytest

from ai_detect import analyze, downloads, fetch, history
from ai_detect.models import REGISTRY

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AI_WORDS = ("furthermore", "additionally", "provides", "seamless", "comprehensive")
AI_TEXT = ("Furthermore, the platform provides a seamless experience for modern teams. "
           "Additionally, it provides comprehensive coverage of every seamless workflow.")
HUMAN_TEXT = ("I do not love the price, though, and my brother thinks it is too slow. "
              "We went back to the old one after about a week of that.")


class FakeBackend:
    device_label = "cpu"

    def __init__(self, name, ai=6.0, human=-6.0):
        self.name, self._ai, self._human = name, ai, human

    def margins(self, texts):
        return [self._ai if any(w in t.lower() for w in AI_WORDS) else self._human for t in texts]


@pytest.fixture
def fake_models(monkeypatch):
    """Score by keyword; no model is downloaded or loaded."""
    def use(ai=6.0, human=-6.0):
        monkeypatch.setattr(
            analyze, "get_detector",
            lambda model, device=None: FakeBackend(REGISTRY.resolve(model).id, ai, human))
    use()
    return use


# --- 1. Playwright present but unable to start --------------------------------

class FakePlaywrightError(Exception):
    pass


def _raiser(error):
    def raise_it(**kwargs):
        raise error
    return raise_it


def _fake_playwright(monkeypatch, start_error=None, launch_error=None):
    class Manager:
        def __enter__(self):
            if start_error:
                raise start_error
            return types.SimpleNamespace(
                chromium=types.SimpleNamespace(launch=_raiser(launch_error)))

        def __exit__(self, *exc):
            return False

    api = types.ModuleType("playwright.sync_api")
    api.Error = FakePlaywrightError
    api.sync_playwright = lambda: Manager()
    pkg = types.ModuleType("playwright")
    pkg.sync_api = api
    monkeypatch.setitem(sys.modules, "playwright", pkg)
    monkeypatch.setitem(sys.modules, "playwright.sync_api", api)


DRIVER_DIED = Exception("Connection closed while reading from the driver")
MISSING_LIBS = FakePlaywrightError(
    "BrowserType.launch: Target page, context or browser has been closed\n"
    "Browser logs:\n\n"
    "chrome-headless-shell: error while loading shared libraries: libnss3.so: "
    "cannot open shared object file: No such file or directory\nCall log:\n  - <launching>")
HOST_DEPS = FakePlaywrightError(
    "BrowserType.launch: \n+------+\n| Host system is missing dependencies to run browsers. |\n"
    "| Please install them with the following command:      |\n"
    "|     sudo playwright install-deps                     |\n+------+")


@pytest.mark.parametrize("kwargs, needle", [
    ({"start_error": DRIVER_DIED}, "Connection closed while reading from the driver"),
    ({"start_error": OSError(8, "Exec format error")}, "Exec format error"),
    ({"launch_error": MISSING_LIBS}, "libnss3.so"),
    ({"launch_error": HOST_DEPS}, "Host system is missing dependencies"),
])
def test_playwright_that_cannot_start_gives_the_install_message(monkeypatch, kwargs, needle):
    _fake_playwright(monkeypatch, **kwargs)
    with pytest.raises(fetch.UrlFetchUnavailable) as info:
        fetch._render("https://example.com/", 5, False)
    message = str(info.value)
    assert fetch.INSTALL_HINT in message
    assert needle in message
    assert "playwright install --with-deps chromium" in message
    assert "apt-get install -y libatomic1" in message


def test_cli_url_scan_prints_no_traceback_when_the_driver_cannot_start(monkeypatch, capsys):
    from ai_detect import cli
    _fake_playwright(monkeypatch, start_error=DRIVER_DIED)
    monkeypatch.setenv("AI_DETECT_ALLOW_PRIVATE_URLS", "1")
    monkeypatch.setattr(cli, "_download", lambda ids: None)
    code = cli.main(["--url", "https://example.com/"])
    err = capsys.readouterr().err
    assert code == 1
    assert "Traceback" not in err
    assert "playwright install chromium" in err
    assert "Connection closed while reading from the driver" in err


def test_a_page_error_is_still_a_page_error(monkeypatch):
    """Only failures to start are turned into the install message."""
    _fake_playwright(monkeypatch, launch_error=FakePlaywrightError(
        "Page.goto: net::ERR_NAME_NOT_RESOLVED at https://x.invalid/"))
    with pytest.raises(fetch.UrlFetchError) as info:
        fetch._render("https://x.invalid/", 5, False)
    assert not isinstance(info.value, fetch.UrlFetchUnavailable)


def test_a_refusal_by_a_running_playwright_is_not_called_an_install_problem(monkeypatch):
    _fake_playwright(monkeypatch, start_error=FakePlaywrightError(
        "It looks like you are using Playwright Sync API inside the asyncio loop."))
    with pytest.raises(fetch.UrlFetchError) as info:
        fetch._render("https://example.com/", 5, False)
    assert not isinstance(info.value, fetch.UrlFetchUnavailable)
    assert "asyncio loop" in str(info.value)


# --- 2. The CLI does not write to history --------------------------------------

def test_a_cli_scan_is_not_saved_to_history(monkeypatch, tmp_path, capsys, fake_models):
    from ai_detect import cli
    monkeypatch.setenv("AI_DETECT_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "_download", lambda ids: None)
    draft = tmp_path / "draft.txt"
    draft.write_text(AI_TEXT, encoding="utf-8")
    before = len(history.list_scans())
    assert cli.main(["--file", str(draft)]) == 0
    assert cli.main(["--text", HUMAN_TEXT, "--json"]) == 0
    capsys.readouterr()
    assert not os.path.exists(history.folder())
    assert len(history.list_scans()) == before
    assert sorted(p.name for p in tmp_path.iterdir()) == ["draft.txt"]


def test_cli_help_says_scans_are_not_saved(capsys):
    from ai_detect import cli
    with pytest.raises(SystemExit):
        cli.main(["--help"])
    out = " ".join(capsys.readouterr().out.split())
    assert "does not save scans" in out and "--export" in out


def test_a_dashboard_scan_is_saved_to_history(monkeypatch, tmp_path, fake_models):
    from ai_detect.web import app
    monkeypatch.setenv("AI_DETECT_HOME", str(tmp_path))
    monkeypatch.setattr(history, "_enabled", True)
    monkeypatch.setattr(app, "_wait_for_models", lambda ids, progress: None)
    report = app.run_scan({"text": AI_TEXT})
    assert os.path.isfile(os.path.join(history.folder(), report["scan_id"] + ".json"))
    history.delete(report["scan_id"])


# --- 3. One verdict and one figure on every surface ----------------------------

def _report(text, fake_models, **margins):
    fake_models(**margins)
    return analyze.analyze(text, models=["gpttrace-150m"])


def test_history_row_carries_the_result_pages_verdict_and_figure(fake_models):
    # A margin of 1.2 is 76.9% raw and under gpttrace-150m's passage operating
    # point, so the raw and calibrated document figures differ.
    report = _report(AI_TEXT, fake_models, ai=1.2)
    a = report["assessment"]
    assert report["document_ai_pct"] != a["ai_pct"]
    row = history._summary(report)
    assert row["verdict"] == a["label"]
    assert row["calibrated_document_pct"] == a["ai_pct"]
    assert row["calibrated_document_pct"] == report["operating_point"]["calibrated_document_pct"]
    assert row["document_ai_pct"] == report["document_ai_pct"]      # still the raw figure
    assert row["raw_scale"] is True                                  # and marked as raw


def test_history_row_for_an_ensemble_is_not_marked_raw(fake_models):
    fake_models()
    report = analyze.analyze(AI_TEXT, models=["gpttrace-150m", "light"])
    row = history._summary(report)
    assert row["raw_scale"] is False
    assert row["calibrated_document_pct"] == report["assessment"]["ai_pct"]


def test_compare_uses_each_sides_assessment(fake_models):
    a = _report(AI_TEXT, fake_models, ai=6.0)
    b = _report(AI_TEXT, fake_models, ai=1.2)
    c = analyze.compare(a, b)
    assert c["verdicts"] == [a["assessment"]["label"], b["assessment"]["label"]]
    assert c["verdicts"][0] != c["verdicts"][1]
    assert not any(v.isupper() for v in c["verdicts"])              # not the legacy LIKELY AI
    assert c["calibrated_document_pct"] == [a["assessment"]["ai_pct"], b["assessment"]["ai_pct"]]
    assert c["document_ai_pct"] == [a["document_ai_pct"], b["document_ai_pct"]]
    assert c["operating_point_flagged"] == [a["operating_point"]["flagged_sentences"],
                                            b["operating_point"]["flagged_sentences"]]
    assert c["raw_scale"] == [True, True]


def test_dashboard_script_shows_calibrated_figures_and_labels_raw_ones():
    with open(os.path.join(ROOT, "ai_detect", "web", "static", "app.js"), encoding="utf-8") as f:
        js = f.read()
    assert "x.calibrated_document_pct" in js
    assert "c.calibrated_document_pct" in js
    assert "Document score, raw" in js
    assert "c.raw_scale" in js and "x.raw_scale" in js


def test_batch_csv_has_the_calibrated_column(fake_models):
    from ai_detect import report as exports
    row = history._summary(_report(AI_TEXT, fake_models, ai=1.2))
    header, line = exports.batch_to_csv([row]).splitlines()[:2]
    cols = header.split(",")
    assert "calibrated_document_pct" in cols and "document_ai_pct" in cols
    value = line.split(",")[cols.index("calibrated_document_pct")]
    assert value == str(row["calibrated_document_pct"])


def test_html_export_shows_the_calibrated_score_and_labels_the_raw_one(fake_models):
    from ai_detect import report as exports
    report = _report(AI_TEXT, fake_models, ai=1.2)
    page = exports.to_html(report)
    assert f"Document score: <b>{report['assessment']['ai_pct']}%</b>" in page
    assert "Document score, raw" in page and f"<b>{report['document_ai_pct']}%</b>" in page
    fake_models()
    both = analyze.analyze(AI_TEXT, models=["gpttrace-150m", "light"])
    page = exports.to_html(both)
    assert f"Document score: <b>{both['assessment']['ai_pct']}%</b>" in page
    assert "Document score, raw" not in page


def test_html_export_labels_each_models_document_score_as_raw(fake_models):
    # The Models table of an ensemble report prints every model's own document
    # probability. It is not the calibrated score above it, so the heading says raw.
    import re
    from ai_detect import report as exports
    fake_models()
    both = analyze.analyze(AI_TEXT, models=["gpttrace-150m", "light"])
    page = exports.to_html(both)
    heads = re.findall(r"<th>(.*?)</th>", page.split("<h2>Models</h2>")[1].split("</table>")[0])
    assert heads == ["Model", "Licence", "RAID rank", "Doc score (raw)", "Flagged"]
    for mid, row in both["per_model"].items():
        assert f'<td class="num">{row["document_ai_pct"]}</td>' in page


def test_cli_prints_the_assessment_and_labels_raw_figures(monkeypatch, capsys, fake_models):
    from ai_detect import cli
    fake_models(ai=1.2)
    monkeypatch.setattr(cli, "_download", lambda ids: None)
    assert cli.main(["--text", AI_TEXT]) == 0
    out = capsys.readouterr().out
    report = _report(AI_TEXT, fake_models, ai=1.2)
    assert f"Assessment: {report['assessment']['label']}" in out
    assert f"{report['assessment']['ai_pct']}%" in out
    assert "raw" in next(ln for ln in out.splitlines() if "Model AI score" in ln)
    assert "raw" in next(ln for ln in out.splitlines() if "Document score" in ln)


# --- 4. The time-left wording --------------------------------------------------

@pytest.mark.parametrize("seconds, text", [
    (None, ""), (0, ""), (1, "less than a minute left"), (6, "less than a minute left"),
    (44, "less than a minute left"), (45, "about 1 min left"), (89, "about 1 min left"),
    (90, "about 2 min left"), (600, "about 10 min left"),
])
def test_eta_text(seconds, text):
    assert downloads.eta_text(seconds) == text


def test_status_message_agrees_with_eta_seconds(monkeypatch):
    import time
    spec = REGISTRY.resolve("light")
    total = 126 * 1024 * 1024
    monkeypatch.setattr(downloads, "is_model_cached", lambda model: False)
    monkeypatch.setitem(downloads._STATE, spec.id, {
        **downloads._blank(spec.id), "state": "downloading", "started": time.time() - 60,
        "bytes_total": total, "bytes_done": int(total * 10 / 11)})
    status = downloads.status("light")
    assert 4 <= status["eta_seconds"] <= 8
    assert "1 min" not in status["message"]
    assert "less than a minute left" in status["message"]


def test_cli_progress_bar_agrees_with_eta_seconds(capsys):
    from ai_detect import cli
    cli._progress_bar({"model": "light", "percent": 91.0, "bytes_total": 126 * 1048576,
                       "eta_seconds": 6})
    err = capsys.readouterr().err
    assert "1 min" not in err and "less than a minute left" in err


def test_dashboard_script_does_not_round_seconds_up_to_a_minute():
    with open(os.path.join(ROOT, "ai_detect", "web", "static", "app.js"), encoding="utf-8") as f:
        js = f.read()
    assert "Math.ceil(m.eta_seconds / 60)" not in js
    assert "etaText(" in js


# --- 5. Screenshots show nothing local -----------------------------------------

def _screenshots_module():
    spec = importlib.util.spec_from_file_location(
        "make_screenshots", os.path.join(ROOT, "scripts", "make_screenshots.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_screenshot_engine_uses_a_neutral_home_and_the_default_port(monkeypatch):
    from ai_detect.web.server import DEFAULT_PORT
    shots = _screenshots_module()
    monkeypatch.setenv("AI_DETECT_PORT", "18765")
    monkeypatch.setenv("AI_DETECT_HOME", os.path.join(tempfile.gettempdir(), "x"))
    home = shots.neutral_home()
    env = shots.engine_env(home)
    assert env["AI_DETECT_HOME"] == home
    assert env["AI_DETECT_PORT"] == str(DEFAULT_PORT)
    assert shots.BASE == f"http://127.0.0.1:{DEFAULT_PORT}"
    assert not shots.shows_something_local(home)


def test_screenshot_script_refuses_a_path_that_would_show_in_a_picture():
    shots = _screenshots_module()
    assert shots.shows_something_local(os.path.join(os.path.expanduser("~"), ".ai-detect"))
    assert shots.shows_something_local(os.path.join(tempfile.gettempdir(), "home0"))
    assert not shots.shows_something_local(shots.neutral_home())
