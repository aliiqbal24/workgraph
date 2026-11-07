"""One persistent local controller per Git project; secrets stay off tool output."""

import fcntl
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time
import signal
import threading
from urllib.request import Request, build_opener, ProxyHandler

from .engine import Engine
from .errors import WorkgraphError


def atomic_json(path, value):
    temporary = path.with_name(path.name + "." + secrets.token_hex(5))
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as file:
        json.dump(value, file)
        file.flush()
        os.fsync(file.fileno())
    temporary.replace(path)


def credentials(engine):
    path = engine.home / "workspace-access.json"
    try:
        value = json.loads(path.read_text())
        if all(
            isinstance(value.get(k), str) and len(value[k]) >= 30
            for k in ("operator", "viewer")
        ):
            return value
    except (OSError, ValueError):
        pass
    value = {k: secrets.token_urlsafe(32) for k in ("operator", "viewer")}
    atomic_json(path, value)
    return value


def healthy(record, access):
    try:
        port = record["port"]
        if type(port) is not int or not 1024 <= port <= 65535:
            return False
        request = Request(
            f"http://127.0.0.1:{port}/api/health",
            headers={"Authorization": "Bearer " + access["viewer"]},
        )
        with build_opener(ProxyHandler({})).open(request, timeout=0.6) as response:
            value = json.load(response)
        return (
            value.get("identity") == record["identity"] and value.get("ready") is True
        )
    except Exception:
        return False


def open_workspace(repo, open_browser=True):
    engine = Engine(repo)
    if not engine.dbpath.exists():
        engine.init()
    engine.home.mkdir(parents=True, exist_ok=True)
    with (engine.home / "workspace-open.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        access = credentials(engine)
        registry = engine.home / "workspace-controller.json"
        try:
            record = json.loads(registry.read_text())
        except (OSError, ValueError):
            record = {}
        reused = healthy(record, access)
        if not reused:
            # A controller may be saving partial work after an explicit stop.
            # Wait for its ownership lock before launching a replacement.
            with (engine.home / "workspace-controller.lock").open("a") as gate:
                deadline = time.monotonic() + 25
                while True:
                    try:
                        fcntl.flock(gate, fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError:
                        if time.monotonic() >= deadline:
                            raise WorkgraphError(
                                "WORKSPACE_BUSY",
                                "The previous workspace is still saving or closing. Its work is preserved; reopen shortly.",
                            )
                        time.sleep(0.15)
                fcntl.flock(gate, fcntl.LOCK_UN)
            log = (engine.home / "workspace-controller.log").open("ab")
            previous = record.get("port", 0)
            argv = [
                sys.executable,
                str(Path(__file__).resolve().parent / "entry.py"),
                "--repo",
                str(engine.repo),
                "workspace-controller",
                "--port",
                str(previous if type(previous) is int else 0),
            ]
            process = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
                close_fds=True,
            )
            log.close()
            deadline = time.monotonic() + 18
            while time.monotonic() < deadline:
                try:
                    record = json.loads(registry.read_text())
                except (OSError, ValueError):
                    record = {}
                if healthy(record, access):
                    break
                if process.poll() is not None:
                    raise WorkgraphError(
                        "WORKSPACE_START_FAILED",
                        "The project workspace could not start. Inspect its local controller log.",
                    )
                time.sleep(0.12)
            else:
                raise WorkgraphError(
                    "WORKSPACE_START_TIMEOUT",
                    "The project workspace is still starting. Open it again shortly; no agent task was started.",
                )
        base = f"http://127.0.0.1:{record['port']}/"
        opened = False
        if (
            open_browser
            and (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))
            and shutil.which("xdg-open")
        ):
            # The operator capability goes directly to the local browser, never
            # into the model-visible response, launch log, or shell command.
            subprocess.Popen(
                [shutil.which("xdg-open"), base + "#token=" + access["operator"]],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            opened = True
        return {
            "workspace": str(engine.repo),
            "url": base + "#view=" + access["viewer"],
            "opened": opened,
            "reused": reused,
            "mode": "read-only link; the local browser receives editing controls privately",
            "conversation": "Opening and browsing do not create an attempt or change this conversation. Continue from a version only when the user requests an edit.",
        }


def run_controller(repo, port=0):
    from .server import Application, make_server

    engine = Engine(repo)
    engine.status()
    lock = (engine.home / "workspace-controller.lock").open("a")
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return
    access = credentials(engine)
    app = Application(engine, access=access)
    try:
        server = make_server(app, port)
    except OSError:
        server = make_server(app, 0)
    identity = secrets.token_hex(16)
    app.identity = identity
    atomic_json(
        engine.home / "workspace-controller.json",
        {"port": server.server_address[1], "identity": identity, "pid": os.getpid()},
    )

    def shutdown(number, frame):
        threading.Thread(target=server.shutdown, daemon=True).start()

    signal.signal(signal.SIGTERM, shutdown)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        lock.close()


def stop_workspace(repo):
    engine = Engine(repo)
    try:
        record = json.loads((engine.home / "workspace-controller.json").read_text())
        access = json.loads((engine.home / "workspace-access.json").read_text())
    except (OSError, ValueError):
        return {"state": "stopped"}
    if not healthy(record, access):
        return {"state": "stopped"}
    request = Request(
        f"http://127.0.0.1:{record['port']}/api/action",
        data=b'{"action":"workspace.stop"}',
        headers={
            "Authorization": "Bearer " + access["operator"],
            "Content-Type": "application/json",
        },
    )
    with build_opener(ProxyHandler({})).open(request, timeout=3) as response:
        return json.load(response)
