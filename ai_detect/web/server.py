"""Starting and finding the local dashboard server.

One stable default port (8765), with automatic fallback to the next free one.
``url()`` always reports the port actually bound. The server listens on
127.0.0.1 only.
"""

import os
import socket
import threading
import time
import webbrowser

DEFAULT_PORT = 8765
HOST = "127.0.0.1"
_LOCK = threading.Lock()
_STATE = {"url": "", "server": None, "thread": None}


def default_port():
    try:
        return int(os.environ.get("AI_DETECT_PORT") or DEFAULT_PORT)
    except ValueError:
        return DEFAULT_PORT


def find_port(preferred=None):
    """The preferred port if free, else the next free one of the 20 after it,
    else whatever the OS hands out."""
    preferred = preferred or default_port()
    for port in [*range(preferred, preferred + 21), 0]:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind((HOST, port))
                return s.getsockname()[1]
            except OSError:
                continue
    raise OSError("No free port for the ai-detect dashboard")


def url():
    """The running dashboard's URL, or '' if it has not been started."""
    return _STATE["url"]


def _make_server(port):
    import uvicorn

    from . import app as webapp
    config = uvicorn.Config(webapp.app, host=HOST, port=port, log_level="warning",
                            access_log=False)
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # we may be on a non-main thread
    _STATE["url"] = webapp.BASE_URL["url"] = f"http://{HOST}:{port}"
    return server


def ensure_started(port=None, open_browser=False):
    """Start the dashboard in a background thread if it is not running yet.
    Returns its URL. Safe to call from any thread, any number of times."""
    with _LOCK:
        thread = _STATE["thread"]
        if thread is None or not thread.is_alive():
            server = _make_server(find_port(port))
            thread = threading.Thread(target=server.run, name="ai-detect-dashboard", daemon=True)
            _STATE.update(server=server, thread=thread)
            thread.start()
            deadline = time.time() + 10
            while not server.started and thread.is_alive() and time.time() < deadline:
                time.sleep(0.05)
    if open_browser:
        webbrowser.open(_STATE["url"])
    return _STATE["url"]


def serve_forever(port=None, open_browser=False):
    """Run the dashboard in the foreground (the ``ai-detect serve`` command)."""
    server = _make_server(find_port(port))
    if open_browser:
        threading.Timer(0.8, lambda: webbrowser.open(_STATE["url"])).start()
    print(f"ai-detect dashboard: {_STATE['url']}   (Ctrl+C to stop)", flush=True)
    server.install_signal_handlers = lambda: None
    try:
        server.run()
    except KeyboardInterrupt:
        pass


def stop():
    server = _STATE["server"]
    if server is not None:
        server.should_exit = True
