"""Owned, bounded development-app processes from immutable saved product states."""

from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from http.client import HTTPConnection
from http.cookies import SimpleCookie
from pathlib import Path
import json
import os
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
from urllib.parse import urlsplit, unquote
from urllib.request import build_opener, ProxyHandler

from .errors import WorkgraphError
from .preview import Page, root_urls
from .product_state import ProductState, project_path


def stop_group(process):
    if process is None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)
    # A parent may have exited while a development server descendant remains.
    try:
        os.killpg(process.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass


@dataclass
class Instance:
    id: str
    revision: str
    fingerprint: str
    profile: dict
    root: Path
    host: str
    fresh: bool = False
    status: str = "preparing"
    url: str | None = None
    error: str | None = None
    process: object = None
    proxy: object = None
    created: float = field(default_factory=time.time)
    touched: float = field(default_factory=time.time)
    closed: bool = False

    def public(self):
        return {
            "id": self.id,
            "revision": self.revision,
            "state": self.status,
            "url": self.url,
            "error": self.error,
            "name": self.profile["name"],
            "fingerprint": self.fingerprint,
            "created": self.created,
        }


class Runtimes:
    HOSTS = [f"127.0.2.{i}" for i in range(1, 9)]

    def __init__(self, studio):
        self.studio = studio
        self.engine = studio.engine
        self.states = ProductState(self.engine)
        self.instances = {}
        self.lock = threading.RLock()
        self.closed = False
        self.parent_port = None
        self.threads = []

    def list(self):
        with self.lock:
            return [
                x.public()
                for x in self.instances.values()
                if not x.closed and not x.fresh
            ]

    def open(self, revision, fresh=False):
        self.studio.revision(revision)
        with self.engine.db() as db:
            state = self.states.get(revision, db)
            profile = self.states.profile(db, revision=revision)
        if not state or not profile:
            raise WorkgraphError(
                "APP_NOT_CONNECTED",
                "Connect a development app recipe to this version before running it.",
            )
        if not shutil.which("bwrap"):
            raise WorkgraphError(
                "SANDBOX_REQUIRED",
                "App previews require bubblewrap. Saved screenshots and source remain available.",
            )
        with self.lock:
            if self.closed:
                raise WorkgraphError(
                    "RUNTIME_CLOSED", "The preview controller is closing."
                )
            if not fresh:
                existing = next(
                    (
                        x
                        for x in self.instances.values()
                        if x.revision == revision
                        and not x.fresh
                        and not x.closed
                        and x.status in ("preparing", "ready")
                    ),
                    None,
                )
                if existing:
                    existing.touched = time.time()
                    return existing
            alive = [x for x in self.instances.values() if not x.closed]
            if len(alive) >= 4:
                idle = sorted(
                    (x for x in alive if not x.fresh and time.time() - x.touched > 90),
                    key=lambda x: x.touched,
                )
                if not idle:
                    raise WorkgraphError(
                        "PREVIEW_CAPACITY",
                        "Four previews are in use. Close one before opening another.",
                    )
                self.stop(idle[0].id)
            hosts = {x.host for x in self.instances.values() if not x.closed}
            host = next(h for h in self.HOSTS if h not in hosts)
            key = "runtime_" + secrets.token_hex(8)
            instance = Instance(
                key,
                revision,
                state["fingerprint"],
                profile,
                self.engine.home / "product" / "runtimes" / key,
                host,
                fresh,
            )
            self.instances[key] = instance
            thread = threading.Thread(target=self._start, args=(instance,), daemon=True)
            self.threads.append(thread)
            thread.start()
            return instance

    def wait(self, instance, timeout=90):
        deadline = time.monotonic() + timeout
        while (
            instance.status == "preparing"
            and time.monotonic() < deadline
            and not instance.closed
        ):
            time.sleep(0.06)
        if instance.status != "ready":
            raise WorkgraphError(
                "APP_START_FAILED",
                instance.error
                or "The app did not become ready. Its saved version is unchanged.",
            )
        return instance

    def _argv(self, instance, argv, port, writable=False):
        replacements = {
            "{port}": str(port),
            "{workspace}": "/app",
            "{data}": "/app/.workgraph-data",
            "{python}": sys.executable,
        }
        values = []
        for arg in argv:
            for key, value in replacements.items():
                arg = arg.replace(key, value)
            values.append(arg)
        binary = shutil.which(values[0])
        if not binary:
            raise WorkgraphError(
                "EXECUTABLE_MISSING", f"The app command {values[0]} is not installed."
            )
        values[0] = binary
        sandbox = [
            shutil.which("bwrap"),
            "--die-with-parent",
            "--unshare-pid",
            "--ro-bind",
            "/usr",
            "/usr",
            "--dev",
            "/dev",
            "--proc",
            "/proc",
            "--tmpfs",
            "/tmp",
        ]
        for path in ("/bin", "/lib", "/lib64"):
            if Path(path).exists():
                sandbox += ["--ro-bind", path, path]
        for path in (
            "/etc/hosts",
            "/etc/resolv.conf",
            "/etc/nsswitch.conf",
            "/etc/ssl",
        ):
            if Path(path).exists():
                sandbox += ["--ro-bind", path, path]
        prefix = Path(sys.prefix).resolve()
        if not prefix.is_relative_to(Path("/usr")):
            sandbox += ["--ro-bind", str(prefix), str(prefix)]
        real = Path(binary).resolve()
        if not real.is_relative_to(Path("/usr")) and not real.is_relative_to(prefix):
            sandbox += ["--ro-bind", str(real), str(real)]
        sandbox += [
            "--bind" if writable else "--ro-bind",
            str(instance.root / "app"),
            "/app",
            "--bind",
            str(instance.root / "app/.workgraph-data"),
            "/app/.workgraph-data",
            "--chdir",
            "/app",
            "--",
            *values,
        ]
        env = {k: os.environ[k] for k in ("LANG", "LC_ALL") if k in os.environ}
        env.update(
            PATH="/usr/bin:/bin:" + str(Path(sys.executable).parent),
            HOME="/tmp",
            TMPDIR="/tmp",
            PYTHONDONTWRITEBYTECODE="1",
            PORT=str(port),
            WORKGRAPH_REVISION=instance.revision,
        )
        for key, value in instance.profile["environment"].items():
            for placeholder, replacement in replacements.items():
                value = value.replace(placeholder, replacement)
            env[key] = value
        return sandbox, env

    def _start(self, instance):
        try:
            app = instance.root / "app"
            app.mkdir(parents=True)
            # Only immutable regular source files are materialized; Git internals,
            # source symlinks and operator metadata never enter the app runtime.
            total = 0
            for name, entry in self.studio.files(instance.revision).items():
                total += entry["size"]
                if total > 250_000_000:
                    raise WorkgraphError(
                        "APP_TOO_LARGE",
                        "This local preview exceeds the 250 MB saved-source limit.",
                    )
                target = project_path(app, name)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(
                    self.studio.read(instance.revision, name, limit=250_000_000)
                )
                target.chmod(0o755 if entry["executable"] else 0o644)
            (app / ".workgraph-data").mkdir(exist_ok=True)
            self.states.restore(instance.revision, app)
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0))
                port = sock.getsockname()[1]
            with (instance.root / "output.log").open("wb") as log:
                for command in instance.profile["prepare"]:
                    if instance.closed:
                        return
                    argv, env = self._argv(instance, command, port, writable=True)
                    process = subprocess.Popen(
                        argv,
                        env=env,
                        stdout=log,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    instance.process = process
                    try:
                        code = process.wait(timeout=60)
                    except subprocess.TimeoutExpired:
                        stop_group(process)
                        raise WorkgraphError(
                            "APP_SETUP_TIMEOUT", "App preparation exceeded 60 seconds."
                        )
                    stop_group(process)
                    if code:
                        raise WorkgraphError(
                            "APP_SETUP_FAILED",
                            "The approved preparation command failed. Open the local runtime log for details.",
                        )
                for name, entry in self.studio.files(instance.revision).items():
                    target = project_path(app, name)
                    if not target.is_file() or target.read_bytes() != self.studio.read(
                        instance.revision, name, limit=250_000_000
                    ):
                        raise WorkgraphError(
                            "SETUP_CHANGED_SOURCE",
                            "Preparation changed saved source. Save those changes as a new version before previewing.",
                        )
                if instance.closed:
                    return
                argv, env = self._argv(instance, instance.profile["command"], port)
                instance.process = subprocess.Popen(
                    argv,
                    env=env,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                )
                opener = build_opener(ProxyHandler({}))
                deadline = time.monotonic() + 30
                ready = False
                time.sleep(0.15)
                while time.monotonic() < deadline and not instance.closed:
                    if instance.process.poll() is not None:
                        break
                    try:
                        with opener.open(
                            f"http://127.0.0.1:{port}" + instance.profile["health"],
                            timeout=0.8,
                        ) as response:
                            ready = 200 <= response.status < 400
                        if ready:
                            break
                    except Exception:
                        time.sleep(0.1)
                if not ready:
                    raise WorkgraphError(
                        "APP_NOT_READY",
                        "The app did not pass its readiness check. Your saved version is unchanged.",
                    )
                instance.proxy = self._proxy(instance, port)
                instance.url = f"http://{instance.host}:{instance.proxy.server_address[1]}/{instance.proxy.ticket}/"
                instance.status = "ready"
                while not instance.closed and not self.closed:
                    if instance.process.poll() is not None:
                        instance.error = "The app process stopped. Reopen this version to start a fresh copy."
                        instance.status = "failed"
                        break
                    if time.time() - instance.touched > 900:
                        break
                    if (instance.root / "output.log").stat().st_size > 20_000_000:
                        instance.error = "The app produced too much output."
                        instance.status = "failed"
                        break
                    time.sleep(0.5)
        except Exception as error:
            instance.error = (
                str(error)
                if isinstance(error, WorkgraphError)
                else f"The preview could not start ({type(error).__name__}). Its saved files are unchanged."
            )
            instance.status = "failed"
        finally:
            stop_group(instance.process)
            if instance.proxy:
                instance.proxy.shutdown()
                instance.proxy.server_close()
            if instance.status != "failed":
                instance.status = "stopped"

    def _proxy(self, instance, backend_port):
        manager = self
        ticket = secrets.token_urlsafe(24)
        prefix = "/" + ticket + "/"
        cookie_prefix = ticket[:8] + "_"

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_GET(self):
                self.forward()

            def do_POST(self):
                self.forward()

            def do_PUT(self):
                self.forward()

            def do_PATCH(self):
                self.forward()

            def do_DELETE(self):
                self.forward()

            def do_OPTIONS(self):
                self.forward()

            def forward(self):
                if self.headers.get(
                    "Host"
                ) != f"{instance.host}:{self.server.server_address[1]}" or not urlsplit(
                    self.path
                ).path.startswith(prefix):
                    return self.reply(404, b"Preview not found.")
                path = self.path[len(prefix) - 1 :]
                if any(p == ".." for p in unquote(urlsplit(path).path).split("/")):
                    return self.reply(404, b"Preview not found.")
                try:
                    length = int(self.headers.get("Content-Length", 0))
                except ValueError:
                    return self.reply(400, b"Invalid request.")
                if not 0 <= length <= 2_000_000:
                    return self.reply(413, b"Request too large.")
                headers = {
                    k: v
                    for k, v in self.headers.items()
                    if k.lower()
                    in ("accept", "content-type", "authorization", "user-agent")
                }
                cookies = SimpleCookie()
                try:
                    cookies.load(self.headers.get("Cookie", ""))
                except Exception:
                    pass
                selected = [
                    name[len(cookie_prefix) :] + "=" + value.coded_value
                    for name, value in cookies.items()
                    if name.startswith(cookie_prefix)
                ]
                if selected:
                    headers["Cookie"] = "; ".join(selected)
                instance.touched = time.time()
                connection = HTTPConnection("127.0.0.1", backend_port, timeout=15)
                try:
                    connection.request(
                        self.command,
                        path,
                        body=self.rfile.read(length) if length else None,
                        headers=headers,
                    )
                    response = connection.getresponse()
                    body = response.read(25_000_001)
                    if len(body) > 25_000_000:
                        return self.reply(502, b"Preview response exceeds its limit.")
                    mime = response.getheader(
                        "Content-Type", "application/octet-stream"
                    )
                    if "text/html" in mime:
                        source = body.decode("utf-8", errors="replace")
                        if "<head" not in source.lower():
                            source = "<head></head>" + source
                        body = "".join(Page(source, prefix, prefix).result).encode()
                        script = manager.bridge(prefix, instance.id)
                        body = (
                            body.replace(b"<head>", b"<head>" + script, 1)
                            if b"<head>" in body
                            else script + body
                        )
                    elif "text/css" in mime:
                        body = root_urls(
                            body.decode("utf-8", errors="replace"), prefix
                        ).encode()
                    elif any(x in mime for x in ("javascript", "ecmascript")):
                        import re

                        body = re.sub(
                            r"""((?:from\s*|import\s*\(?\s*)['"])/(?!/)""",
                            lambda m: m[1] + prefix,
                            body.decode("utf-8", errors="replace"),
                        ).encode()
                    self.send_response(response.status)
                    self.send_header("Content-Type", mime)
                    self.send_header("Content-Length", str(len(body)))
                    self.send_header("Cache-Control", "no-store")
                    self.send_header("X-Content-Type-Options", "nosniff")
                    self.send_header("Referrer-Policy", "no-referrer")
                    parents = f"http://127.0.0.1:{manager.parent_port} http://localhost:{manager.parent_port}"
                    self.send_header(
                        "Content-Security-Policy",
                        f"default-src 'self'; script-src 'self' 'unsafe-inline' blob:; style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; font-src 'self' data:; media-src 'self' blob:; connect-src 'self'; object-src 'none'; frame-src 'none'; frame-ancestors {parents}",
                    )
                    location = response.getheader("Location")
                    if (
                        location
                        and location.startswith("/")
                        and not location.startswith("//")
                    ):
                        self.send_header("Location", prefix + location.lstrip("/"))
                    for key, value in response.getheaders():
                        if key.lower() == "set-cookie":
                            jar = SimpleCookie()
                            try:
                                jar.load(value)
                                for name, morsel in jar.items():
                                    rewritten = SimpleCookie()
                                    rewritten[cookie_prefix + name] = morsel.value
                                    rewritten[cookie_prefix + name]["path"] = prefix
                                    if morsel["httponly"]:
                                        rewritten[cookie_prefix + name]["httponly"] = (
                                            True
                                        )
                                    rewritten[cookie_prefix + name]["samesite"] = "Lax"
                                    self.send_header(
                                        "Set-Cookie",
                                        rewritten.output(header="").strip(),
                                    )
                            except Exception:
                                pass
                    self.end_headers()
                    try:
                        self.wfile.write(body)
                    except (BrokenPipeError, ConnectionResetError):
                        pass
                except Exception:
                    self.reply(
                        502,
                        b"The development app did not respond. Reopen the saved version to retry.",
                    )
                finally:
                    connection.close()

            def reply(self, status, body):
                self.send_response(status)
                self.send_header("Content-Type", "text/plain")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                try:
                    self.wfile.write(body)
                except (BrokenPipeError, ConnectionResetError):
                    pass

        server = ThreadingHTTPServer((instance.host, 0), Handler)
        server.ticket = ticket
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server

    def bridge(self, prefix, instance):
        code = (Path(__file__).parent / "web/recorder.js").read_text()
        config = json.dumps(
            {
                "prefix": prefix,
                "instance": instance,
                "operator": f"http://127.0.0.1:{self.parent_port}",
            }
        )
        return (
            "<script>window.__workgraph="
            + config
            + ";</script><script>"
            + code
            + "</script>"
        ).encode()

    def touch(self, key):
        with self.lock:
            instance = self.instances.get(key)
            if not instance or instance.closed:
                raise WorkgraphError(
                    "RUNTIME_NOT_FOUND",
                    "This interactive copy is closed. Open the saved version again.",
                )
            instance.touched = time.time()
            return instance

    def stop(self, key):
        with self.lock:
            instance = self.instances.get(key)
            if instance:
                instance.closed = True
                stop_group(instance.process)
        return {"id": key, "state": "stopped"}

    def close(self):
        self.closed = True
        for key in list(self.instances):
            self.stop(key)
        for thread in self.threads:
            thread.join(timeout=5)
