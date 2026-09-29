#!/usr/bin/env python3
"""tunnel.py - Self-hosted state publishing via localtunnel.

Background
----------
The bot used to publish ``state.json`` to a GitHub Gist every minute, but
GitHub rate-limits those writes (HTTP 403). This module instead serves the
bot's local ``state.json`` from a tiny HTTP server on the Oracle VM and
exposes it on a public HTTPS URL via **localtunnel** (free, no signup).

Only the Python standard library is required. Node.js and localtunnel are
bootstrapped automatically (downloaded/installed as the unprivileged bot
user - no ``sudo`` needed).

Public API
----------
    start_tunnel(state_file_path=None) -> str
        Start the HTTP server + localtunnel, return the public HTTPS URL.
        Idempotent: if already running, the existing URL is returned.

    stop_tunnel() -> None
        Clean shutdown of the tunnel and the HTTP server.

    get_public_url() -> str
        The current public URL, or "" when the tunnel is not running.

Typical usage from main.py::

    import tunnel
    url = tunnel.start_tunnel()   # e.g. https://memecoin-ayoub-bot.loca.lt
    ...
    tunnel.stop_tunnel()
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

NODE_VERSION = "v20.11.0"
NODE_DIST_URL = (
    "https://nodejs.org/dist/v20.11.0/node-v20.11.0-linux-arm64.tar.xz"
)
NODE_HOME = os.path.expanduser("~/node")  # user-local install, no sudo
BOT_DIR = os.path.dirname(os.path.abspath(__file__))
# Default: the same path the bot uses for its local state (state.json next
# to the bot sources). main.py may pass an explicit path instead.
DEFAULT_STATE_FILE = os.path.join(BOT_DIR, "state.json")
DEFAULT_PORT = 8080          # local port the HTTP server binds
PREFERRED_SUBDOMAIN = "memecoin-ayoub-bot"
URL_RE = re.compile(r"your url is:\s*(https://\S+)", re.IGNORECASE)
MAX_PORT_TRIES = 10          # 8080 .. 8089 when 8080 is busy
URL_WAIT_TIMEOUT = 90        # seconds to wait for localtunnel's URL line
RESTART_DELAY = 10           # seconds between auto-restart attempts

_lock = threading.Lock()
_state = {
    "process": None,        # subprocess.Popen for localtunnel
    "url": "",              # current public HTTPS URL
    "port": None,           # local port actually bound
    "state_file": "",       # absolute path being served
    "httpd": None,          # ThreadingHTTPServer instance
    "stop_event": None,     # threading.Event signalling shutdown
    "monitor_thread": None, # background thread restarting a dead tunnel
}


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

def _log(msg: str) -> None:
    """Log with the [TUNNEL] prefix so tunnel output is easy to grep."""
    print(f"[TUNNEL] {msg}", flush=True)


# ---------------------------------------------------------------------------
# 1. Node.js bootstrap (no sudo, runs as the unprivileged ubuntu user)
# ---------------------------------------------------------------------------

def _node_bin() -> str | None:
    """Return a usable `node` binary path, or None if not installed."""
    found = shutil.which("node")
    if found:
        return found
    local = os.path.join(NODE_HOME, "bin", "node")
    if os.path.isfile(local) and os.access(local, os.X_OK):
        return local
    return None


def _extract_node_archive(archive: str, dest: str) -> None:
    """Safely extract the Node.js tar.xz into *dest* (path-traversal safe)."""
    dest_abs = os.path.abspath(dest)
    with tarfile.open(archive, "r:xz") as tf:
        for member in tf.getmembers():
            target = os.path.abspath(os.path.join(dest_abs, member.name))
            if not target.startswith(dest_abs + os.sep):
                raise RuntimeError(
                    f"Unsafe path in Node.js archive: {member.name}"
                )
        if sys.version_info >= (3, 12):
            tf.extractall(dest_abs, filter="data")
        else:
            tf.extractall(dest_abs)


def _ensure_node() -> str:
    """Make sure Node.js is available.

    Returns a PATH value that includes the node/npm binaries, so it can be
    passed to subprocesses via env.
    """
    existing = _node_bin()
    if existing:
        _log(f"Node.js already available: {existing}")
        bin_dir = os.path.dirname(existing)
        return os.pathsep.join([bin_dir, os.environ.get("PATH", "")])

    # The Oracle VM is ARM64: fetch the official linux-arm64 LTS binary.
    _log(f"Node.js not found - downloading Node {NODE_VERSION} (linux-arm64)...")
    archive = os.path.join(
        os.path.expanduser("~"),
        f"node-{NODE_VERSION}-linux-arm64.tar.xz",
    )
    try:
        urllib.request.urlretrieve(NODE_DIST_URL, archive)
    except Exception as exc:
        raise RuntimeError(
            f"Failed to download Node.js from {NODE_DIST_URL}: {exc}"
        ) from exc

    tmp_dir = archive + ".extract"
    os.makedirs(tmp_dir, exist_ok=True)
    try:
        _extract_node_archive(archive, tmp_dir)
        extracted = [
            d for d in os.listdir(tmp_dir)
            if d.startswith("node-") and os.path.isdir(os.path.join(tmp_dir, d))
        ]
        if not extracted:
            raise RuntimeError("Node.js archive had no top-level directory")
        if os.path.isdir(NODE_HOME):
            shutil.rmtree(NODE_HOME)
        shutil.move(os.path.join(tmp_dir, extracted[0]), NODE_HOME)
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
        try:
            os.remove(archive)
        except OSError:
            pass

    node_bin = _node_bin()
    if not node_bin:
        raise RuntimeError("Node.js installed but `node` binary not found")
    _log(f"Node.js {NODE_VERSION} installed to {NODE_HOME}")
    bin_dir = os.path.dirname(node_bin)
    return os.pathsep.join([bin_dir, os.environ.get("PATH", "")])


# ---------------------------------------------------------------------------
# 2. localtunnel setup
# ---------------------------------------------------------------------------

def _ensure_localtunnel(path_env: str) -> str:
    """Install localtunnel locally (`npm install localtunnel`, no sudo/-g).

    Returns the path to the `npx` binary to launch it with.
    """
    env = dict(os.environ, PATH=path_env)
    marker = os.path.join(BOT_DIR, "node_modules", "localtunnel")
    if os.path.isdir(marker):
        _log("localtunnel already installed in bot directory")
    else:
        _log("Installing localtunnel locally (npm install localtunnel)...")
        proc = subprocess.run(
            ["npm", "install", "localtunnel"],
            cwd=BOT_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if proc.returncode != 0:
            raise RuntimeError(
                "npm install localtunnel failed:\n" + proc.stderr[-2000:]
            )
        _log("localtunnel installed in bot directory")

    npx = shutil.which("npx", path=path_env)
    if not npx:
        # Fall back to the npx shipped with the user-local Node install.
        npx = os.path.join(NODE_HOME, "bin", "npx")
    return npx


def _spawn_localtunnel(
    npx: str, port: int, subdomain: str | None, path_env: str
) -> subprocess.Popen:
    """Launch `npx localtunnel --port <port> [--subdomain <sub>]`."""
    args = [npx, "localtunnel", "--port", str(port)]
    if subdomain:
        args += ["--subdomain", subdomain]
    _log("Starting: " + " ".join(args[1:]))  # skip local npx path
    return subprocess.Popen(
        args,
        cwd=BOT_DIR,
        env=dict(os.environ, PATH=path_env),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )


def _read_public_url(proc: subprocess.Popen,
                     timeout: int = URL_WAIT_TIMEOUT) -> str:
    """Read process stdout until `your url is: https://...` appears."""
    deadline = time.time() + timeout
    assert proc.stdout is not None
    while time.time() < deadline:
        if proc.poll() is not None:
            break  # process exited before printing a URL
        line = proc.stdout.readline()
        if not line:
            time.sleep(0.2)
            continue
        line = line.strip()
        if line:
            _log(f"localtunnel: {line}")
        match = URL_RE.search(line)
        if match:
            return match.group(1).rstrip(".")
    return ""


def _kill_process(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _start_tunnel_process(
    npx: str, port: int, path_env: str
) -> tuple[subprocess.Popen, str]:
    """Start localtunnel, preferring our subdomain, else a random one.

    Returns (process, public_url). The *actual* URL is always returned, so
    callers cope with the requested subdomain being taken.
    """
    proc = _spawn_localtunnel(npx, port, PREFERRED_SUBDOMAIN, path_env)
    url = _read_public_url(proc)
    if url:
        if PREFERRED_SUBDOMAIN not in url:
            # localtunnel assigned a random subdomain because ours was taken.
            _log(f"Requested subdomain taken; using fallback URL: {url}")
        else:
            _log(f"Tunnel established: {url}")
        return proc, url

    _log("Preferred subdomain unavailable - retrying with a random subdomain")
    _kill_process(proc)
    proc = _spawn_localtunnel(npx, port, None, path_env)
    url = _read_public_url(proc)
    if not url:
        _kill_process(proc)
        raise RuntimeError("localtunnel did not print a public URL")
    _log(f"Tunnel established (random subdomain): {url}")
    return proc, url


# ---------------------------------------------------------------------------
# 3. HTTP server - serve state.json on localhost
# ---------------------------------------------------------------------------

class _StateHandler(BaseHTTPRequestHandler):
    """Serve only the bot's state file as JSON; 404 for anything else."""

    state_file = DEFAULT_STATE_FILE  # set per server instance at startup

    def _serve_state(self) -> None:
        try:
            with open(self.state_file, "rb") as fh:
                body = fh.read()
        except FileNotFoundError:
            body = b"{}"  # state not written yet - serve empty JSON
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = self.path.split("?", 1)[0]
        if path in ("/", "/state.json", "/index.html"):
            self._serve_state()
        else:
            self.send_error(404, "Not found")

    def log_message(self, fmt: str, *args: object) -> None:
        pass  # keep stdout for [TUNNEL] logs only


def _start_http_server(state_file: str) -> tuple[ThreadingHTTPServer, int]:
    """Bind 127.0.0.1:8080 (or the next free port) in a background thread."""
    _StateHandler.state_file = os.path.abspath(state_file)
    last_err: OSError | None = None
    for port in range(DEFAULT_PORT, DEFAULT_PORT + MAX_PORT_TRIES):
        try:
            httpd = ThreadingHTTPServer(("127.0.0.1", port), _StateHandler)
        except OSError as exc:
            last_err = exc
            _log(f"Port {port} already in use, trying next port...")
            continue
        thread = threading.Thread(
            target=httpd.serve_forever, name="tunnel-http", daemon=True
        )
        thread.start()
        if port == DEFAULT_PORT:
            _log(f"Serving state file on http://127.0.0.1:{port}")
        else:
            _log(f"Port {DEFAULT_PORT} busy - serving on http://127.0.0.1:{port}")
        return httpd, port
    raise RuntimeError(
        f"Could not bind any port {DEFAULT_PORT}-"
        f"{DEFAULT_PORT + MAX_PORT_TRIES - 1}: {last_err}"
    )


# ---------------------------------------------------------------------------
# 5. Robustness - auto-restart the tunnel if it crashes
# ---------------------------------------------------------------------------

def _monitor_loop(npx: str, port: int, path_env: str,
                  stop_event: threading.Event) -> None:
    """Background watchdog: restart localtunnel if its process dies."""
    while not stop_event.wait(5):
        with _lock:
            proc = _state["process"]
            if stop_event.is_set() or proc is None:
                return
            alive = proc.poll() is None
        if alive:
            continue
        _log("localtunnel process died - restarting...")
        time.sleep(RESTART_DELAY)
        if stop_event.is_set():
            return
        try:
            new_proc, new_url = _start_tunnel_process(npx, port, path_env)
        except Exception as exc:
            _log(f"Tunnel restart failed: {exc} (will retry)")
            continue
        with _lock:
            _state["process"] = new_proc
            _state["url"] = new_url
        _log(f"Tunnel restarted: {new_url}")


# ---------------------------------------------------------------------------
# 4. Public API
# ---------------------------------------------------------------------------

def start_tunnel(state_file_path: str | None = None) -> str:
    """Start the HTTP server + localtunnel and return the public HTTPS URL.

    Idempotent: if the tunnel is already running, the existing URL is
    returned without starting anything new.
    """
    state_file = os.path.abspath(state_file_path or DEFAULT_STATE_FILE)
    with _lock:
        proc = _state["process"]
        if proc is not None and proc.poll() is None and _state["url"]:
            _log(f"Tunnel already running: {_state['url']}")
            return _state["url"]
        if proc is not None:
            _kill_process(proc)  # stale entry - clean up before restarting

    _log(f"Starting tunnel for state file: {state_file}")
    path_env = _ensure_node()             # 1. Node.js bootstrap
    npx = _ensure_localtunnel(path_env)   # 2. localtunnel setup

    httpd, port = _start_http_server(state_file)  # 3. HTTP server
    try:
        proc, url = _start_tunnel_process(npx, port, path_env)
    except Exception:
        httpd.shutdown()
        httpd.server_close()
        raise

    stop_event = threading.Event()
    monitor = threading.Thread(
        target=_monitor_loop,
        args=(npx, port, path_env, stop_event),
        name="tunnel-monitor",
        daemon=True,
    )
    with _lock:
        _state.update(
            process=proc,
            url=url,
            port=port,
            state_file=state_file,
            httpd=httpd,
            stop_event=stop_event,
            monitor_thread=monitor,
        )
    monitor.start()
    _log(f"Tunnel ready: {url}  (state: {state_file})")
    return url


def stop_tunnel() -> None:
    """Clean shutdown of the tunnel process and the HTTP server."""
    with _lock:
        proc = _state["process"]
        httpd = _state["httpd"]
        stop_event = _state["stop_event"]
        if stop_event is not None:
            stop_event.set()  # tell the monitor thread to exit
    _log("Stopping tunnel...")
    _kill_process(proc)
    if httpd is not None:
        try:
            httpd.shutdown()
            httpd.server_close()
        except Exception as exc:
            _log(f"HTTP server shutdown issue: {exc}")
    with _lock:
        _state.update(
            process=None,
            url="",
            port=None,
            state_file="",
            httpd=None,
            stop_event=None,
            monitor_thread=None,
        )
    _log("Tunnel stopped")


def get_public_url() -> str:
    """Return the current public HTTPS URL, or "" if not running."""
    with _lock:
        proc = _state["process"]
        if proc is None or proc.poll() is not None:
            return ""
        return _state["url"]


# ---------------------------------------------------------------------------
# Manual smoke test:  python3 tunnel.py [state_file]
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    _path = sys.argv[1] if len(sys.argv) > 1 else None
    try:
        print(start_tunnel(_path))
        _log("Press Ctrl+C to stop.")
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        stop_tunnel()
