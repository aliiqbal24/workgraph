"""Asynchronous actual app captures and independently replayed protected flows."""

import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import queue
import re
import selectors
import shutil
import subprocess
import sys
import threading
import time
import uuid

from .behaviors import Behaviors
from .errors import WorkgraphError
from .product_state import ProductState, fingerprint
from .runtime import stop_group

_BROWSER_PYTHON = None


def browser_python():
    global _BROWSER_PYTHON
    if _BROWSER_PYTHON and Path(_BROWSER_PYTHON).exists():
        return _BROWSER_PYTHON
    candidates = [
        os.environ.get("WORKGRAPH_BROWSER_PYTHON"),
        sys.executable,
        str(Path.home() / ".local/share/workgraph/runtime/bin/python"),
    ]
    for candidate in dict.fromkeys(x for x in candidates if x):
        if not Path(candidate).is_file():
            continue
        try:
            result = subprocess.run(
                [candidate, "-c", "import playwright.sync_api; import PIL"],
                capture_output=True,
                timeout=8,
            )
            if result.returncode == 0:
                _BROWSER_PYTHON = candidate
                return candidate
        except (OSError, subprocess.TimeoutExpired):
            continue
    return None


class Artifacts:
    def __init__(self, studio, runtimes, previews, enabled=True):
        self.studio = studio
        self.engine = studio.engine
        self.runtimes = runtimes
        self.previews = previews
        self.behaviors = Behaviors(studio)
        self.states = ProductState(self.engine)
        self.home = self.engine.home / "product"
        self.media = self.home / "media"
        self.media.mkdir(parents=True, exist_ok=True)
        self.queue = queue.Queue(maxsize=40)
        self.pending = set()
        self.lock = threading.Lock()
        self.closed = threading.Event()
        self.worker = None
        self.controller = (self.home / "capture-controller.lock").open("a")
        self.owns = False
        try:
            fcntl.flock(self.controller, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.owns = True
        except BlockingIOError:
            pass
        self.python = browser_python() if enabled else None
        if self.owns:
            with self.engine.db() as db:
                db.execute(
                    "UPDATE product_artifacts SET state='interrupted',error='Capture was interrupted. Refresh this version to try again.' WHERE state IN ('queued','capturing')"
                )
                db.execute(
                    "UPDATE product_flow_runs SET state='interrupted',updated=? WHERE state IN ('queued','running')",
                    (time.time(),),
                )
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def capabilities(self):
        return {
            "available": bool(self.python),
            "controller": self.owns,
            "browser": "Chromium",
            "setup": "Install workgraph-agent[browser] and Chromium, or set WORKGRAPH_BROWSER_PYTHON to an environment with Playwright and Pillow.",
        }

    def import_media(self, path):
        path = Path(path)
        if path.stat().st_size > 64_000_000:
            raise WorkgraphError(
                "MEDIA_TOO_LARGE",
                "This browser recording exceeds the 64 MB artifact limit.",
            )
        suffix = path.suffix.lower()
        if suffix not in (".jpg", ".png", ".webm"):
            raise WorkgraphError("INVALID_MEDIA", "Unsupported browser artifact.")
        content = path.read_bytes()
        key = hashlib.sha256(content).hexdigest() + suffix
        destination = self.media / key
        if not destination.exists():
            temporary = self.media / (key + ".tmp-" + uuid.uuid4().hex[:6])
            temporary.write_bytes(content)
            temporary.replace(destination)
        return key

    def file(self, key):
        if not isinstance(key, str) or not re.fullmatch(
            r"[a-f0-9]{64}\.(?:jpg|png|webm)", key
        ):
            raise WorkgraphError(
                "MEDIA_NOT_FOUND", "This saved artifact does not exist."
            )
        path = self.media / key
        if not path.is_file():
            raise WorkgraphError(
                "MEDIA_NOT_FOUND", "This saved artifact is unavailable."
            )
        return path

    def gallery_basis(self, revision):
        state = self.states.get(revision)
        return fingerprint(
            {
                "revision": revision,
                "tree": self.studio.revision(revision)["tree_oid"],
                "state": state["fingerprint"] if state else None,
                "capture": "chromium-gallery-v1",
            }
        )

    def request(self, revision, force=False):
        if self.closed.is_set():
            raise WorkgraphError(
                "CAPTURE_STOPPED", "The capture controller is closing."
            )
        self.studio.revision(revision)
        if not self.owns:
            raise WorkgraphError(
                "OTHER_CONTROLLER",
                "The original project workspace manages its visual captures.",
            )
        if not self.python:
            return {
                "revision": revision,
                "state": "unavailable",
                "message": self.capabilities()["setup"],
            }
        state = self.states.get(revision)
        if not state and not self.studio.preview_entry(revision):
            return {"revision": revision, "state": "unsupported"}
        basis = self.gallery_basis(revision)
        flow_basis = self.behaviors.basis(revision)
        flows = self.behaviors.list(revision)
        with self.lock, self.engine.db() as db:
            if revision in self.pending:
                return {"revision": revision, "state": "queued"}
            current = db.execute(
                "SELECT * FROM product_artifacts WHERE revision_id=?", (revision,)
            ).fetchone()
            flow = db.execute(
                "SELECT * FROM product_flow_runs WHERE revision_id=? AND fingerprint=? ORDER BY created DESC LIMIT 1",
                (revision, flow_basis),
            ).fetchone()
            gallery = (
                force
                or not current
                or current["fingerprint"] != basis
                or current["state"] == "interrupted"
            )
            verify = bool(flows) and (
                force or not flow or flow["state"] == "interrupted"
            )
            if not gallery and not verify:
                return {
                    "revision": revision,
                    "state": current["state"] if current else "ready",
                }
            if self.queue.full():
                return {"revision": revision, "state": "waiting"}
            run_id = "run_" + uuid.uuid4().hex[:16] if verify else None
            if gallery:
                db.execute(
                    "INSERT INTO product_artifacts VALUES (?,?, 'queued','{}',NULL,?) ON CONFLICT(revision_id) DO UPDATE SET fingerprint=excluded.fingerprint,state='queued',error=NULL,updated=excluded.updated",
                    (revision, basis, time.time()),
                )
            if verify:
                now = time.time()
                db.execute(
                    "INSERT INTO product_flow_runs VALUES (?,?,?,'queued','[]',?,?)",
                    (run_id, revision, flow_basis, now, now),
                )
            self.pending.add(revision)
            self.queue.put(
                {
                    "revision": revision,
                    "gallery": gallery,
                    "run": run_id,
                    "flows": flows,
                    "basis": basis,
                    "flow_basis": flow_basis,
                }
            )
        return {"revision": revision, "state": "queued", "run": run_id}

    def observe(self, history):
        if not self.owns or not self.python:
            return
        heads = {p["head"] for p in history["paths"] if p["head"]}
        parents = {
            v["parent"] for v in history["versions"] if v["parent"] and v["id"] in heads
        }
        wanted = (
            heads
            | parents
            | {v["id"] for v in history["versions"] if v["starred"]}
            | {history["current"]}
        )
        # Include meaningful saved milestones, bounded so opening a huge repository
        # never queues an unbounded amount of browser work.
        wanted.update(v["id"] for v in history["versions"][-12:])
        for version in history["versions"]:
            if version["id"] in wanted:
                try:
                    self.request(version["id"])
                except WorkgraphError:
                    pass

    def _browser(self, command):
        if self.closed.is_set():
            raise WorkgraphError("CAPTURE_STOPPED", "Capture controller is closing.")
        if self.worker is None or self.worker.poll() is not None:
            log = (self.home / "browser-worker.log").open("ab")
            self.worker = subprocess.Popen(
                [self.python, str(Path(__file__).parent / "browser_worker.py")],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=log,
                text=True,
                bufsize=1,
                start_new_session=True,
                env=os.environ.copy(),
            )
            log.close()
        self.worker.stdin.write(json.dumps(command) + "\n")
        self.worker.stdin.flush()
        watcher = selectors.DefaultSelector()
        watcher.register(self.worker.stdout, selectors.EVENT_READ)
        deadline = time.monotonic() + 160
        try:
            while time.monotonic() < deadline and not self.closed.is_set():
                if watcher.select(0.25):
                    line = self.worker.stdout.readline()
                    if not line:
                        break
                    result = json.loads(line)
                    if not result.get("ok"):
                        raise WorkgraphError(
                            "CAPTURE_FAILED",
                            result.get(
                                "error", "The browser capture could not finish."
                            ),
                        )
                    return result
            stop_group(self.worker)
            self.worker = None
            raise WorkgraphError(
                "CAPTURE_TIMEOUT",
                "The browser did not finish this capture. Saved source and data remain available.",
            )
        finally:
            watcher.close()

    def _address(self, revision):
        state = self.states.get(revision)
        if state:
            instance = self.runtimes.open(revision, fresh=True)
            self.runtimes.wait(instance)
            return instance.url, instance
        entry = self.studio.preview_entry(revision)
        if not entry:
            raise WorkgraphError(
                "PREVIEW_UNAVAILABLE",
                "This saved version has no connected app or static preview.",
            )
        return self.previews.base + "/" + revision + "/" + entry, None

    def _loop(self):
        while not self.closed.is_set():
            try:
                job = self.queue.get(timeout=0.2)
            except queue.Empty:
                continue
            revision = job["revision"]
            instance = None
            try:
                directory = self.home / "captures" / revision / uuid.uuid4().hex[:8]
                directory.mkdir(parents=True)
                if job["gallery"]:
                    with self.engine.db() as db:
                        db.execute(
                            "UPDATE product_artifacts SET state='capturing',updated=? WHERE revision_id=?",
                            (time.time(), revision),
                        )
                    address, instance = self._address(revision)
                    with self.engine.db() as db:
                        profile = self.states.profile(db, revision=revision)
                    screens = (
                        profile["screens"]
                        if profile
                        else [
                            {
                                "name": "Desktop",
                                "path": "/",
                                "width": 1280,
                                "height": 800,
                            },
                            {
                                "name": "Mobile",
                                "path": "/",
                                "width": 390,
                                "height": 844,
                            },
                        ]
                    )
                    # Static preview addresses already identify their entry document.
                    result = self._browser(
                        {
                            "kind": "gallery",
                            "url": address,
                            "screens": screens,
                            "output": str(directory / "gallery"),
                        }
                    )
                    images = []
                    for image in result["images"]:
                        images.append(
                            {
                                **image,
                                "file": self.import_media(image["file"]),
                                "thumb": self.import_media(image["thumb"]),
                            }
                        )
                    manifest = {
                        "images": images,
                        "browser": result["browser"],
                        "captured": time.time(),
                        "basis": job["basis"],
                        "scope": "Actual isolated saved product state; interactive preview changes are not written back.",
                    }
                    with self.engine.db() as db:
                        db.execute(
                            "UPDATE product_artifacts SET state='ready',manifest=?,error=NULL,updated=? WHERE revision_id=?",
                            (json.dumps(manifest), time.time(), revision),
                        )
                    if instance:
                        self.runtimes.stop(instance.id)
                        instance = None
                if job["run"]:
                    with self.engine.db() as db:
                        db.execute(
                            "UPDATE product_flow_runs SET state='running',updated=? WHERE id=?",
                            (time.time(), job["run"]),
                        )
                    results = []
                    for flow in job["flows"]:
                        if self.closed.is_set():
                            break
                        address, instance = self._address(revision)
                        baselines = {
                            step["baseline"]: str(self.file(step["baseline"]))
                            for step in flow["definition"]["steps"]
                            if step["action"] == "visual"
                        }
                        result = self._browser(
                            {
                                "kind": "flow",
                                "url": address,
                                "flow": flow,
                                "baselines": baselines,
                                "output": str(directory / flow["id"]),
                            }
                        )
                        result.update(
                            id=flow["id"],
                            name=flow["name"],
                            fingerprint=flow["fingerprint"],
                        )
                        result.pop("ok", None)
                        result["screenshot"] = self.import_media(result["screenshot"])
                        if result.get("video"):
                            result["video"] = self.import_media(result["video"])
                        results.append(result)
                        if instance:
                            self.runtimes.stop(instance.id)
                            instance = None
                        with self.engine.db() as db:
                            db.execute(
                                "UPDATE product_flow_runs SET results=?,updated=? WHERE id=?",
                                (json.dumps(results), time.time(), job["run"]),
                            )
                    status = (
                        "passed"
                        if results
                        and all(r["passed"] for r in results)
                        and len(results) == len(job["flows"])
                        else "failed"
                    )
                    with self.engine.db() as db:
                        db.execute(
                            "UPDATE product_flow_runs SET state=?,results=?,updated=? WHERE id=?",
                            (status, json.dumps(results), time.time(), job["run"]),
                        )
            except Exception as error:
                message = (
                    str(error)
                    if isinstance(error, WorkgraphError)
                    else f"Capture could not finish ({type(error).__name__})."
                )
                with self.engine.db() as db:
                    if job["gallery"]:
                        db.execute(
                            "UPDATE product_artifacts SET state='failed',error=?,updated=? WHERE revision_id=? AND state!='ready'",
                            (message, time.time(), revision),
                        )
                    if job["run"]:
                        db.execute(
                            "UPDATE product_flow_runs SET state='error',results=?,updated=? WHERE id=?",
                            (
                                json.dumps(
                                    [
                                        {
                                            "passed": False,
                                            "error": message,
                                            "name": "Verification could not run",
                                        }
                                    ]
                                ),
                                time.time(),
                                job["run"],
                            ),
                        )
            finally:
                if instance:
                    self.runtimes.stop(instance.id)
                with self.lock:
                    self.pending.discard(revision)
                self.queue.task_done()
        stop_group(self.worker)

    def records(self):
        with self.engine.db() as db:
            return {
                row["revision_id"]: {
                    **dict(row),
                    "manifest": json.loads(row["manifest"]),
                }
                for row in db.execute("SELECT * FROM product_artifacts")
            }

    def close(self):
        self.closed.set()
        stop_group(self.worker)
        self.thread.join(timeout=8)
        self.controller.close()
