"""Regression tests for the November 2026 code-review findings.

No network, no model and no browser: resolvers, the download manager, the
engine child and the clock are all stubbed.
"""

import os
import socket
import subprocess
import sys
import tempfile
import threading
import time

import pytest

from ai_detect import downloads, fetch, report


# ---------------------------------------------------------------------------
# 1 and 10: the download manager
# ---------------------------------------------------------------------------

@pytest.fixture
def failing_download(monkeypatch):
    """A model that is never cached and whose download always fails."""
    calls = []

    def fake_download(model, on_progress=None):
        spec = downloads.REGISTRY.resolve(model)
        calls.append(spec.id)
        with downloads._LOCK:
            downloads._STATE[spec.id] = {**downloads._blank(spec.id), "state": "failed",
                                         "error": "ConnectionError: simulated outage"}
        return downloads.status(spec.id)

    monkeypatch.setattr(downloads, "is_model_cached", lambda model: False)
    monkeypatch.setattr(downloads, "download", fake_download)
    monkeypatch.setattr(downloads, "_STATE", {})
    monkeypatch.setattr(downloads, "_THREADS", {})
    return calls


def _join(model_id):
    downloads._THREADS[model_id].join(timeout=5)


def test_ensure_starts_a_missing_download_once_and_does_not_restart_a_failed_one(failing_download):
    ready, statuses = downloads.ensure(["light"])
    assert not ready
    _join("light")
    for _ in range(3):
        ready, statuses = downloads.ensure(["light"])
    assert failing_download == ["light"]
    assert not ready
    assert statuses[0]["status"] == "failed"
    assert "simulated outage" in statuses[0]["message"]


def test_explicit_start_retries_a_failed_download(failing_download):
    downloads.ensure(["light"])
    _join("light")
    downloads.start("light")
    _join("light")
    assert failing_download == ["light", "light"]


def test_a_failed_model_that_has_since_been_fetched_elsewhere_reads_as_ready(failing_download, monkeypatch):
    downloads.ensure(["light"])
    _join("light")
    assert downloads.status("light")["status"] == "failed"
    monkeypatch.setattr(downloads, "is_model_cached", lambda model: True)
    ready, statuses = downloads.ensure(["light"])
    assert ready and statuses[0]["status"] == "ready" and statuses[0]["error"] is None


def test_wait_for_models_raises_with_the_reason_when_a_download_fails(failing_download):
    from ai_detect.web import app
    done = {}

    def run():
        try:
            app._wait_for_models(["light"], lambda event: None)
        except RuntimeError as e:
            done["error"] = str(e)

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    thread.join(timeout=10)
    assert not thread.is_alive(), "_wait_for_models never returned"
    assert "simulated outage" in done["error"]
    assert failing_download == ["light"]


def test_download_unsubscribes_its_progress_listener_even_when_it_fails(monkeypatch):
    def boom(spec):
        raise OSError("no network")

    monkeypatch.setattr(downloads, "_file_plan", boom)
    monkeypatch.setattr(downloads, "is_model_cached", lambda model: False)
    monkeypatch.setattr(downloads, "_STATE", {})
    monkeypatch.setattr(downloads, "_LISTENERS", [])
    seen = []
    result = downloads.download("light", on_progress=seen.append)
    assert result["status"] == "failed"
    assert seen and seen[-1]["status"] == "failed"
    assert downloads._LISTENERS == []


# ---------------------------------------------------------------------------
# 2: private-address guard
# ---------------------------------------------------------------------------

def _resolver(*addresses):
    def resolve(host, *args, **kwargs):
        return [(socket.AF_INET6 if ":" in a else socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0))
                for a in addresses]
    return resolve


@pytest.fixture
def no_private(monkeypatch):
    monkeypatch.delenv(fetch.ALLOW_PRIVATE_ENV, raising=False)


@pytest.mark.parametrize("url", [
    "http://127.0.0.1/", "http://127.0.0.1:8765/api/state", "http://127.8.9.10/",
    "http://localhost/", "http://LOCALHOST:3000/", "http://app.localhost/", "http://localhost./",
    "http://10.0.0.5/", "http://172.16.0.1/", "http://172.31.255.254/", "http://192.168.1.1/admin",
    "http://169.254.169.254/latest/meta-data/", "http://100.64.0.1/", "http://100.127.255.254/",
    "http://0.0.0.0/", "http://224.0.0.1/", "http://239.255.255.250/", "http://240.0.0.1/",
    "http://255.255.255.255/",
    "http://[::1]/", "http://[::]/", "http://[fe80::1]/", "http://[fc00::1]/", "http://[fd12:3456::1]/",
    "http://[ff02::1]/", "http://[::ffff:127.0.0.1]/", "http://[::ffff:10.0.0.1]/",
    "http://[64:ff9b::7f00:1]/", "http://[2002:7f00:1::]/", "https://user:pw@192.168.0.10:8443/x",
    "ws://127.0.0.1:9222/devtools",
])
def test_private_and_local_addresses_are_refused(no_private, url):
    assert fetch.blocked_reason(url, resolve=_resolver("93.184.216.34"))
    with pytest.raises(fetch.PrivateAddressError) as e:
        fetch.check_public_url(url, resolve=_resolver("93.184.216.34"))
    assert fetch.ALLOW_PRIVATE_ENV in str(e.value)


@pytest.mark.parametrize("address", ["127.0.0.1", "10.1.2.3", "192.168.0.4", "169.254.169.254",
                                     "100.64.1.1", "::1", "fe80::1", "fd00::1", "0.0.0.0"])
def test_a_name_that_resolves_to_a_private_address_is_refused(no_private, address):
    reason = fetch.blocked_reason("https://intranet.example.com/", resolve=_resolver(address))
    assert "intranet.example.com" in reason and address in reason


def test_a_name_with_one_private_address_among_public_ones_is_refused(no_private):
    assert fetch.blocked_reason("https://mixed.example.com/",
                                resolve=_resolver("93.184.216.34", "10.0.0.1"))


@pytest.mark.parametrize("url", ["https://example.com/", "http://93.184.216.34/page",
                                 "https://[2606:2800:220:1:248:1893:25c8:1946]/",
                                 "http://172.32.0.1/", "http://100.128.0.1/", "http://11.0.0.1/"])
def test_public_addresses_pass(no_private, url):
    assert fetch.blocked_reason(url, resolve=_resolver("93.184.216.34")) == ""
    fetch.check_public_url(url, resolve=_resolver("93.184.216.34"))


def test_non_network_schemes_are_not_judged(no_private):
    for url in ("file:///C:/pages/saved.html", "data:text/html,<p>x</p>", "about:blank",
                "blob:https://example.com/1234"):
        assert fetch.blocked_reason(url, resolve=_resolver("127.0.0.1")) == ""


def test_an_unresolvable_name_is_left_to_the_browser(no_private):
    def resolve(host, *args, **kwargs):
        raise socket.gaierror("no such host")
    assert fetch.blocked_reason("https://nope.invalid/", resolve=resolve) == ""


def test_the_env_switch_allows_private_addresses(monkeypatch):
    monkeypatch.setenv(fetch.ALLOW_PRIVATE_ENV, "1")
    assert fetch.private_urls_allowed()
    fetch.check_public_url("http://127.0.0.1:8000/")
    monkeypatch.setenv(fetch.ALLOW_PRIVATE_ENV, "0")
    assert not fetch.private_urls_allowed()


def test_fetch_url_refuses_a_private_address_before_starting_a_browser(no_private, monkeypatch):
    def no_render(*args, **kwargs):
        raise AssertionError("the browser must not start for a refused URL")
    monkeypatch.setattr(fetch, "_render", no_render)
    with pytest.raises(fetch.PrivateAddressError) as e:
        fetch.fetch_url("http://localhost:8765/")
    assert "localhost" in str(e.value) and "loopback" in str(e.value)


def test_the_request_guard_remembers_hosts_and_records_refusals(no_private):
    lookups = []

    def resolve(host, *args, **kwargs):
        lookups.append(host)
        return _resolver("10.0.0.9" if host == "inside.example.com" else "93.184.216.34")(host)

    guard = fetch._Guard(resolve=resolve)
    assert guard.allows("https://example.com/a") and guard.allows("https://example.com/b")
    assert not guard.allows("https://inside.example.com/x")
    assert not guard.allows("http://127.0.0.1:1/")
    assert guard.allows("file:///C:/x.html")
    assert lookups == ["example.com", "inside.example.com"]
    assert [url for url, _ in guard.refused] == ["https://inside.example.com/x", "http://127.0.0.1:1/"]


# ---------------------------------------------------------------------------
# 9: one deadline for the whole render
# ---------------------------------------------------------------------------

def test_deadline_hands_out_the_time_remaining_then_raises_the_timeout_error():
    now = [100.0]
    deadline = fetch._Deadline(10, "https://example.com/", clock=lambda: now[0])
    assert deadline.ms() == 10000
    now[0] += 7.5
    assert deadline.ms() == 2500
    assert deadline.ms(cap=1000) == 1000
    now[0] += 2.5
    with pytest.raises(fetch.UrlFetchError) as e:
        deadline.ms()
    assert str(e.value) == "Timed out after 10s loading https://example.com/"


# ---------------------------------------------------------------------------
# 5: the HTML report
# ---------------------------------------------------------------------------

def _report(**extra):
    return {
        "scan_id": "abc", "models": ["light"], "model_ai_pct": 71.0, "document_ai_pct": 80.0,
        "words": 20, "ai_count": 1, "human_count": 0, "skipped_count": 0, "total": 1,
        "sentences": [{"sentence": "Furthermore, it is seamless.", "label": "AI", "ai_prob": 0.93,
                       "kind": "paragraph", "block": 0, "why": [], "diagnostics": []}],
        "text_metrics": {}, "pattern_totals": {}, "tells": {"structure": [], "visual": []},
        **extra,
    }


def test_html_report_prints_the_perplexity_figures_under_their_real_keys():
    perplexity = {"model": "gpt2", "per_sentence": [41.2], "document": 41.2, "mean": 43.7,
                  "burstiness": 12.5, "burstiness_cv": 0.29, "sentences_scored": 1, "note": "A readout."}
    page = report.to_html(_report(perplexity=perplexity))
    section = page.split("<h2>Perplexity</h2>")[1].split("</section>")[0]
    assert 'Document perplexity: <b class="num">41.2</b>' in section
    assert 'Mean sentence perplexity: <b class="num">43.7</b>' in section
    assert 'Burstiness: <b class="num">12.5</b>' in section
    assert "0.29" in section


def test_html_report_shows_a_missing_perplexity_figure_as_not_available():
    perplexity = {"document": None, "mean": None, "burstiness": None, "burstiness_cv": None}
    section = report.to_html(_report(perplexity=perplexity)).split("<h2>Perplexity</h2>")[1]
    assert "None" not in section.split("</section>")[0]


def test_html_report_has_no_em_dash():
    page = report.to_html(_report())
    assert "\u2014" not in page and "\u2013" not in page
    assert "Furthermore, it is seamless." in page and "93%" in page


# ---------------------------------------------------------------------------
# 7: uploaded .html temp files
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path))
    return tmp_path


HTML_UPLOAD = {"file_content": "<html><body><p>Hello there.</p></body></html>", "file_name": "page.html"}


def test_scan_job_removes_the_upload_when_the_model_id_is_bad(temp_dir):
    from ai_detect.web import app
    with pytest.raises(ValueError):
        app._scan_job({**HTML_UPLOAD, "models": "no-such-model"})
    assert list(temp_dir.iterdir()) == []


def test_scan_job_removes_the_upload_after_the_scan(temp_dir, monkeypatch):
    from ai_detect.web import app
    seen = []

    def fake_scan(source, **kwargs):
        seen.append(os.path.isfile(source["file"]))
        return {"scan_id": "s1"}

    monkeypatch.setattr(app, "run_scan", fake_scan)
    fn = app._scan_job(dict(HTML_UPLOAD))
    assert len(list(temp_dir.iterdir())) == 1
    assert fn(lambda event: None) == {"scan_id": "s1"}
    assert seen == [True] and list(temp_dir.iterdir()) == []


def test_compare_job_removes_both_uploads_after_the_scan(temp_dir, monkeypatch):
    from ai_detect.web import app
    monkeypatch.setattr(app, "run_scan", lambda source, **kw: {"scan_id": source["file"][-9:]})
    monkeypatch.setattr(app, "compare", lambda a, b: {})
    fn = app._compare_job({"a": dict(HTML_UPLOAD), "b": dict(HTML_UPLOAD)})
    assert len(list(temp_dir.iterdir())) == 2
    fn(lambda event: None)
    assert list(temp_dir.iterdir()) == []


def test_compare_job_removes_both_uploads_when_a_scan_fails(temp_dir, monkeypatch):
    from ai_detect.web import app

    def boom(source, **kw):
        raise RuntimeError("scan failed")

    monkeypatch.setattr(app, "run_scan", boom)
    fn = app._compare_job({"a": dict(HTML_UPLOAD), "b": dict(HTML_UPLOAD)})
    with pytest.raises(RuntimeError):
        fn(lambda event: None)
    assert list(temp_dir.iterdir()) == []


def test_compare_job_removes_the_first_upload_when_the_second_side_is_empty(temp_dir):
    from ai_detect.web import app
    with pytest.raises(ValueError):
        app._compare_job({"a": dict(HTML_UPLOAD), "b": {}})
    assert list(temp_dir.iterdir()) == []


# ---------------------------------------------------------------------------
# 3 and 6: the MCP server's engine
# ---------------------------------------------------------------------------

server = pytest.importorskip("ai_detect.server")


@pytest.mark.parametrize("state, expected", [
    ({"version": server.__version__, "models": []}, True),
    ({"version": "1.0.0"}, False),
    ({"version": server.__version__ + ".dev1"}, False),
    ({"models": []}, False),
    ({}, False),
])
def test_is_engine_needs_this_package_version(monkeypatch, state, expected):
    monkeypatch.setattr(server, "_http", lambda url, **kw: state)
    assert server._is_engine("http://127.0.0.1:8765") is expected


@pytest.mark.parametrize("error", [OSError("refused"), ValueError("HTTP 404")])
def test_is_engine_is_false_when_nothing_answers(monkeypatch, error):
    def fail(url, **kw):
        raise error
    monkeypatch.setattr(server, "_http", fail)
    assert server._is_engine("http://127.0.0.1:8765") is False


def test_is_engine_is_false_for_a_non_object_answer(monkeypatch):
    monkeypatch.setattr(server, "_http", lambda url, **kw: ["version"])
    assert server._is_engine("http://127.0.0.1:8765") is False


def _child(code):
    return subprocess.Popen([sys.executable, "-c", code], stdin=subprocess.DEVNULL,
                            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)


@pytest.fixture
def engine(monkeypatch, tmp_path):
    """_start_engine with the child replaced by a small script."""
    monkeypatch.setenv("AI_DETECT_HOME", str(tmp_path))
    monkeypatch.setattr(server, "_engine", {"url": "", "process": None, "error": None, "owned": False})
    spawned = []

    def use(code, answers=False):
        def spawn(log):
            spawned.append(_child(code))
            return spawned[-1]
        monkeypatch.setattr(server, "_spawn_engine", spawn)
        monkeypatch.setattr(server, "_is_engine", lambda url: answers and "18999" in url)
        return spawned

    yield use
    for process in spawned:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def test_start_engine_times_out_on_a_silent_child_and_terminates_it(engine, monkeypatch):
    spawned = engine("import time; time.sleep(60)")
    monkeypatch.setattr(server, "ENGINE_START_TIMEOUT", 1.0)
    started = time.time()
    with pytest.raises(RuntimeError) as e:
        server._start_engine()
    assert time.time() - started < 8
    assert "did not start" in str(e.value) and "engine.log" in str(e.value)
    assert spawned[0].wait(timeout=5) is not None
    assert server._engine["process"] is None and server._engine["url"] == ""
    assert server._engine_lock.acquire(timeout=1)
    server._engine_lock.release()


def test_start_engine_reports_a_child_that_exits_without_waiting_for_the_timeout(engine, monkeypatch):
    engine("import sys; sys.exit(3)")
    monkeypatch.setattr(server, "ENGINE_START_TIMEOUT", 30.0)
    started = time.time()
    with pytest.raises(RuntimeError):
        server._start_engine()
    assert time.time() - started < 10


def test_start_engine_returns_the_url_and_keeps_draining_stdout(engine, monkeypatch):
    # After its address line the child writes far more than a pipe buffer holds.
    # It can only finish if something is still reading its stdout.
    spawned = engine(
        "import sys\n"
        "print('ai-detect dashboard: http://127.0.0.1:18999   (Ctrl+C to stop)', flush=True)\n"
        "for _ in range(4000): sys.stdout.write('x' * 500 + '\\n')\n"
        "sys.stdout.flush()\n", answers=True)
    monkeypatch.setattr(server, "ENGINE_START_TIMEOUT", 20.0)
    assert server._start_engine() == "http://127.0.0.1:18999"
    assert server._engine["owned"] is True
    assert spawned[0].wait(timeout=15) == 0


def test_start_engine_does_not_attach_to_another_version_on_the_default_port(engine, monkeypatch):
    spawned = engine("print('ai-detect dashboard: http://127.0.0.1:18999', flush=True)\n"
                     "import time; time.sleep(30)", answers=True)
    monkeypatch.setenv("AI_DETECT_PORT", "18998")  # _is_engine says no for this port
    assert server._start_engine() == "http://127.0.0.1:18999"
    assert len(spawned) == 1 and server._engine["owned"] is True


# ---------------------------------------------------------------------------
# 8: the engine's parent watch
# ---------------------------------------------------------------------------

def _sleeper(seconds):
    return subprocess.Popen([sys.executable, "-c", f"import time; time.sleep({seconds})"],
                            stdin=subprocess.DEVNULL)


def test_pid_alive_tells_a_running_process_from_a_finished_one():
    from ai_detect import cli
    assert cli._pid_alive(os.getpid())
    child = _sleeper(0)
    child.wait(timeout=20)
    assert not cli._pid_alive(child.pid)


@pytest.mark.skipif(os.name != "nt", reason="elsewhere the watch is on the parent pid only")
def test_wait_until_gone_returns_when_the_process_exits():
    from ai_detect import cli
    child = _sleeper(1.5)
    started = time.time()
    cli._wait_until_gone(child.pid, poll=0.1)
    assert child.wait(timeout=5) == 0
    assert time.time() - started >= 1.0


@pytest.mark.skipif(os.name != "nt", reason="the handle fallback is Windows-only")
def test_wait_until_gone_polls_when_the_handle_cannot_be_opened(monkeypatch):
    from ai_detect import cli
    monkeypatch.setattr(cli, "_open_process", lambda pid, access: None)
    polled = []
    alive = iter([True, True, False])
    monkeypatch.setattr(cli, "_pid_alive", lambda pid: polled.append(pid) or next(alive))
    cli._wait_until_gone(4242, poll=0.01)
    assert polled == [4242, 4242, 4242]


@pytest.mark.skipif(os.name != "nt", reason="ctypes prototypes are Windows-only")
def test_windows_handle_functions_declare_pointer_sized_handles():
    import ctypes
    from ctypes import wintypes
    from ai_detect import cli
    k32 = cli._kernel32()
    assert k32.OpenProcess.restype is wintypes.HANDLE
    assert k32.OpenProcess.argtypes == [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    assert k32.WaitForSingleObject.argtypes == [wintypes.HANDLE, wintypes.DWORD]
    assert k32.WaitForSingleObject.restype is wintypes.DWORD
    assert ctypes.sizeof(wintypes.HANDLE) == ctypes.sizeof(ctypes.c_void_p)
