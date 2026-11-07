"""Loopback-only operator UI. Bearer authentication and strict browser origins."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import urlparse, parse_qs

from .engine import Engine, WorkgraphError
from .example import Example
from .studio import Studio
from .preview import Previews
from .jobs import Jobs
from .runtime import Runtimes
from .artifacts import Artifacts
from .behaviors import Behaviors
from .product_state import ProductState
import time
import uuid
import shutil


class Application:
    def __init__(
        self, engine, example=None, access=None, capture=True, autocapture=True
    ):
        self.engine = engine
        self.example = example
        self.token = access["operator"] if access else secrets.token_urlsafe(32)
        self.viewer = access["viewer"] if access else secrets.token_urlsafe(32)
        self.identity = secrets.token_hex(16)
        self.media_ticket = secrets.token_urlsafe(24)
        self.shutdown = None
        self.closing = False
        self.assets = Path(__file__).parent / "web"
        self.studio = Studio(engine)
        self.previews = Previews(self.studio)
        self.jobs = Jobs(self.studio)
        self.runtimes = Runtimes(self.studio)
        self.behaviors = Behaviors(self.studio)
        self.artifacts = Artifacts(
            self.studio, self.runtimes, self.previews, enabled=capture
        )
        self.stopping = threading.Event()
        self.autocapture = autocapture
        self.jobs.on_saved = lambda revision: self.artifacts.request(revision)
        self.observer = threading.Thread(target=self._observe, daemon=True)

    def _observe(self):
        while not self.stopping.wait(4):
            try:
                self.artifacts.observe(self.studio.history())
            except Exception:
                pass  # Individual capture errors are durable UI state.

    def close(self):
        self.closing = True
        self.stopping.set()
        self.jobs.close()
        self.artifacts.close()
        self.runtimes.close()
        self.previews.close()
        if self.observer.is_alive():
            self.observer.join(timeout=5)

    def studio_state(self):
        result = self.studio.history()
        result["preview_base"] = self.previews.base
        result["runtimes"] = {
            name: bool(shutil.which(name)) for name in ("hermes", "codex", "claude")
        }
        result["artifacts"] = self.artifacts.records()
        result["media_base"] = "/media/" + self.media_ticket + "/"
        result["capture"] = self.artifacts.capabilities()
        result["apps"] = self.runtimes.list()
        states = ProductState(self.engine)
        for version in result["versions"]:
            state = states.get(version["id"])
            version["product_state"] = (
                {
                    "fingerprint": state["fingerprint"],
                    "files": len(state["manifest"]["files"]),
                    "missing": state["manifest"]["missing"],
                }
                if state
                else None
            )
            version["protection"] = self.behaviors.latest(version["id"])
            version["flows"] = self.behaviors.list(version["id"])
        with self.engine.db() as db:
            result["lineage"] = [
                dict(row) for row in db.execute("SELECT * FROM product_lineage")
            ]
        sample = self.engine.home / "playground.json"
        if sample.exists():
            try:
                result["sample"] = json.loads(sample.read_text())
            except ValueError:
                pass
        return result

    def dispatch(self, args):
        action = args.get("action")
        key = args.get("request_id")
        if action == "workspace.stop":
            self.closing = True
            if self.shutdown:
                threading.Timer(0.3, self.shutdown).start()
            return {
                "state": "stopping",
                "message": "The local workspace is stopping. Saved history remains available. Ask your agent to open Workgraph to return.",
            }
        if action == "studio.focus":
            self.studio.revision(args["revision"])
            camera = args.get("camera")
            if camera is not None and (
                not isinstance(camera, dict)
                or set(camera) != {"x", "y", "z"}
                or any(
                    type(v) not in (int, float) or not -1e7 < v < 1e7
                    for v in camera.values()
                )
                or not 0.12 <= camera["z"] <= 2
            ):
                raise WorkgraphError("INVALID_VIEW", "Choose a valid canvas position.")
            with self.engine.db() as db:
                db.execute(
                    "INSERT OR REPLACE INTO studio_choices VALUES ('focus',?)",
                    (json.dumps({"revision": args["revision"], "camera": camera}),),
                )
            return {"revision": args["revision"], "mode": "browsing"}
        if action == "runtime.open":
            return self.runtimes.open(args["revision"]).public()
        if action == "runtime.stop":
            return self.runtimes.stop(args["instance"])
        if action == "runtime.touch":
            return self.runtimes.touch(args["instance"]).public()
        if action == "capture.refresh":
            return self.artifacts.request(args["revision"], force=True)
        if action == "behavior.protect":
            result = self.behaviors.create(
                args["revision"], args["name"], args["definition"], key
            )
            self.artifacts.request(args["revision"])
            return result
        if action == "runtime.save":
            instance = self.runtimes.instances.get(args["instance"])
            if not instance:
                raise WorkgraphError(
                    "RUNTIME_NOT_FOUND", "This interactive copy is no longer available."
                )

            def save(request):
                self.runtimes.stop(instance.id)
                result = self.studio.branch(
                    instance.revision,
                    args.get("name", "An interactive exploration"),
                    request_id=request + ":branch",
                )
                ProductState(self.engine).copy_databases(
                    instance.root / "app", Path(result["workspace"]), instance.profile
                )
                saved = self.engine.checkpoint(
                    result["attempt"],
                    args.get("name", "Saved interactions"),
                    select=False,
                    request_id=request + ":save",
                )
                self.engine.transition(result["attempt"], "paused")
                self.artifacts.request(saved["revision"])
                with self.engine.db() as db:
                    return self.engine._finish(
                        db,
                        request,
                        {**result, **saved},
                        "product.interactions.saved",
                        saved["revision"],
                    )

            return self.engine._request(
                "runtime.save",
                {"instance": instance.id, "name": args.get("name")},
                save,
                key,
                exclusive=False,
            )
        if action == "studio.adapt":
            return self.jobs.adapt(
                args["target"],
                args["source"],
                args["prompt"],
                args.get("runtime", "codex"),
                args.get("kind", "borrow"),
                key,
            )
        if action == "app.configure":

            def connect(request):
                states = ProductState(self.engine)
                profile = states.configure(args["definition"])
                result = self.studio.branch(
                    args["revision"],
                    "Connect " + profile["name"],
                    request_id=request + ":branch",
                )
                with self.engine.db() as db:
                    db.execute(
                        "INSERT OR REPLACE INTO app_attempt_profiles VALUES (?,?)",
                        (result["attempt"], profile["id"]),
                    )
                if args.get("import_data") is True:
                    states.copy_databases(
                        self.engine.repo, Path(result["workspace"]), profile
                    )
                saved = self.engine.checkpoint(
                    result["attempt"],
                    "Connected " + profile["name"],
                    select=False,
                    request_id=request + ":save",
                )
                self.engine.transition(result["attempt"], "paused")
                self.artifacts.request(saved["revision"])
                with self.engine.db() as db:
                    return self.engine._finish(
                        db,
                        request,
                        {**result, **saved},
                        "app.connected",
                        saved["revision"],
                    )

            return self.engine._request(
                "app.configure",
                {
                    "revision": args["revision"],
                    "definition": args["definition"],
                    "import_data": args.get("import_data", False),
                },
                connect,
                key,
                exclusive=False,
            )
        if action == "studio.start":
            return self.studio.start(args.get("name", "Starting point"), key)
        if action == "studio.branch":
            return self.studio.branch(
                args["revision"],
                args["name"],
                runtime=args.get("runtime", "local"),
                prompt=args.get("prompt"),
                request_id=key,
            )
        if action == "studio.note":
            return self.studio.note(
                args["revision"], args.get("label"), args.get("starred"), key
            )
        if action == "studio.path.rename":
            return self.studio.rename_path(args["path"], args["name"], key)
        if action == "studio.choose":
            return self.studio.choose(args["revision"], key)
        if action == "studio.compare":
            return self.studio.compare(args["left"], args["right"])
        if action == "studio.combine":
            return self.studio.combine(
                args["target"],
                args["source"],
                args["paths"],
                args.get("name", "Combined direction"),
                key,
            )
        if action == "studio.agent":
            reuse = args.get("reuse_path", False)
            if not isinstance(reuse, bool):
                raise WorkgraphError(
                    "INVALID_ARGUMENTS",
                    "Choose whether to continue this path or create another.",
                )
            return self.jobs.start(
                args["revision"],
                args["name"],
                args["runtime"],
                args["prompt"],
                key,
                reuse_path=reuse,
            )
        if action == "studio.cancel":
            return self.jobs.cancel(args["job"])
        if action == "studio.file":
            content = self.studio.read(args["revision"], args["path"], limit=1000000)
            return {
                "path": args["path"],
                "content": content.decode("utf-8", errors="replace"),
            }
        if action == "studio.files":
            return {
                "revision": args["revision"],
                "files": list(self.studio.files(args["revision"])),
            }
        if action == "open":
            return self.engine.begin(
                args.get("intent", ""),
                session=args.get("session", "operator"),
                runtime=args.get("runtime", "local"),
                depends_on=args.get("depends_on", []),
                request_id=key,
            )
        if action == "checkpoint":
            return self.engine.checkpoint(
                args["attempt"],
                summary=args.get("summary"),
                plan=args.get("plan"),
                decisions=args.get("decisions"),
                questions=args.get("questions"),
                request_id=key,
            )
        if action == "resume":
            return self.engine.resume(args["attempt"])
        if action == "takeover":
            return self.engine.takeover(
                args["attempt"],
                args.get("session", "replacement"),
                args.get("runtime", "local"),
                key,
            )
        if action == "transition":
            return self.engine.transition(
                args["attempt"], args["state"], request_id=key
            )
        if action == "fork":
            return self.engine.begin(
                "Alternative approach",
                session=args.get("session", "alternative"),
                runtime=args.get("runtime", "local"),
                from_revision=args["revision"],
                request_id=key,
            )
        if action == "reconcile":
            return self.engine.reconcile(args["attempt"], request_id=key)
        if action == "select":
            return self.engine.select(args["revision"], key)
        if action == "propose":
            return self.engine.compose(args["revisions"], key)
        if action == "verify":
            return self.engine.verify(args["candidate"], args["check"], request_id=key)
        if action == "accept":
            return self.engine.land(args["candidate"], key)
        if action == "diff":
            return self.engine.diff(args.get("revision"), args.get("candidate"))
        if action == "recover":
            return self.engine.recover()
        if action == "example.advance" and self.example:
            return self.example.advance(args.get("phase"))
        raise WorkgraphError("INVALID_ACTION", "Unknown operator action.")


def make_server(application, port=8731):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Workgraph/1.0"

        def log_message(self, *args):
            pass

        def send(
            self,
            code,
            data,
            content_type="application/json; charset=utf-8",
            download=None,
            cache="no-store",
        ):
            body = (
                data
                if isinstance(data, bytes)
                else json.dumps(data, ensure_ascii=False).encode()
            )
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", cache)
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if download:
                self.send_header(
                    "Content-Disposition", f'attachment; filename="{download}"'
                )
            preview = (application.previews.base or "").split("/", 3)[:3]
            origin = "/".join(preview) if preview else "'none'"
            apps = " ".join("http://" + host + ":*" for host in Runtimes.HOSTS)
            self.send_header(
                "Content-Security-Policy",
                f"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self' blob:; connect-src 'self'; frame-src {origin} {apps}; frame-ancestors 'none'; base-uri 'none'",
            )
            self.end_headers()
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def authorized(self, write=False):
            host = self.headers.get("Host", "")
            actual_port = self.server.server_address[1]
            allowed = {f"127.0.0.1:{actual_port}", f"localhost:{actual_port}"}
            if host not in allowed:
                self.send(403, {"error": "INVALID_HOST"})
                return False
            origin = self.headers.get("Origin")
            if origin and origin not in {"http://" + h for h in allowed}:
                self.send(403, {"error": "INVALID_ORIGIN"})
                return False
            value = self.headers.get("Authorization", "")
            operator = secrets.compare_digest(value, "Bearer " + application.token)
            viewing = secrets.compare_digest(value, "Bearer " + application.viewer)
            if not operator and not viewing:
                self.send(
                    401,
                    {
                        "error": "UNAUTHORIZED",
                        "message": "Open the private URL printed by workgraph serve.",
                    },
                )
                return False
            if write and not operator:
                self.send(
                    403,
                    {
                        "error": "VIEW_ONLY",
                        "message": "This link is for viewing. Run workgraph open locally to open editing controls privately.",
                    },
                )
                return False
            if write and application.closing:
                self.send(
                    503,
                    {
                        "error": "WORKSPACE_CLOSING",
                        "message": "The workspace is saving and stopping. Ask your agent to open Workgraph to return.",
                    },
                )
                return False
            self.operator = operator
            return True

        def do_GET(self):
            route = urlparse(self.path).path
            if route == "/api/health":
                if not self.authorized():
                    return
                return self.send(
                    200,
                    {
                        "identity": application.identity,
                        "ready": not application.closing,
                    },
                )
            if route.startswith("/media/"):
                parts = route.split("/")
                if (
                    len(parts) != 4
                    or not secrets.compare_digest(parts[2], application.media_ticket)
                    or self.headers.get("Host")
                    not in {
                        f"127.0.0.1:{self.server.server_address[1]}",
                        f"localhost:{self.server.server_address[1]}",
                    }
                ):
                    return self.send(404, {"error": "NOT_FOUND"})
                try:
                    path = application.artifacts.file(parts[3])
                    mime = {
                        ".jpg": "image/jpeg",
                        ".png": "image/png",
                        ".webm": "video/webm",
                    }[path.suffix]
                    return self.send(
                        200,
                        path.read_bytes(),
                        mime,
                        cache="private, max-age=31536000, immutable",
                    )
                except WorkgraphError:
                    return self.send(404, {"error": "NOT_FOUND"})
            if route == "/api/export":
                if not self.authorized():
                    return
                revision = parse_qs(urlparse(self.path).query).get("revision", [""])[0]
                try:
                    content = application.studio.archive(revision)
                    return self.send(
                        200,
                        content,
                        "application/zip",
                        download="workgraph-" + revision[-8:] + ".zip",
                    )
                except WorkgraphError as error:
                    return self.send(409, error.as_dict())
            if route == "/favicon.ico":
                return self.send(204, b"", "image/x-icon")
            if route == "/api/studio":
                if not self.authorized():
                    return
                return self.send(
                    200, {**application.studio_state(), "operator": self.operator}
                )
            if route == "/api/state":
                if not self.authorized():
                    return
                result = application.engine.status()
                result["example"] = (
                    application.example.state() if application.example else None
                )
                return self.send(200, result)
            files = {
                "/": ("canvas.html", "text/html; charset=utf-8"),
                "/classic": ("studio.html", "text/html; charset=utf-8"),
                "/canvas.js": ("canvas.js", "text/javascript; charset=utf-8"),
                "/canvas.css": ("canvas.css", "text/css; charset=utf-8"),
                "/engineering": ("index.html", "text/html; charset=utf-8"),
                "/studio.js": ("studio.js", "text/javascript; charset=utf-8"),
                "/studio.css": ("studio.css", "text/css; charset=utf-8"),
                "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                "/style.css": ("style.css", "text/css; charset=utf-8"),
            }
            if route not in files:
                return self.send(404, {"error": "NOT_FOUND"})
            name, mime = files[route]
            self.send(200, (application.assets / name).read_bytes(), mime)

        def do_POST(self):
            if not self.authorized(write=True):
                return
            if urlparse(self.path).path != "/api/action":
                return self.send(404, {"error": "NOT_FOUND"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 1 or length > 65536:
                    return self.send(413, {"error": "BODY_SIZE"})
                args = json.loads(self.rfile.read(length))
                if not isinstance(args, dict):
                    raise ValueError("Expected an object")
                result = application.dispatch(args)
                self.send(200, result)
            except WorkgraphError as error:
                self.send(409, error.as_dict())
            except (ValueError, KeyError, TypeError) as error:
                self.send(
                    400,
                    {
                        "error": "INVALID_ARGUMENTS",
                        "message": "The request is missing a required field or contains an invalid value.",
                    },
                )
            except Exception as error:
                self.send(
                    500,
                    {
                        "error": "OPERATION_FAILED",
                        "message": f"The operation did not complete ({type(error).__name__}). Inspect workgraph doctor.",
                    },
                )

    class Server(ThreadingHTTPServer):
        def server_close(self):
            application.close()
            super().server_close()

    server = Server(("127.0.0.1", port), Handler, bind_and_activate=False)
    try:
        server.server_bind()
        server.server_activate()
    except OSError:
        # A failed bind must not tear down the app before the broker retries
        # another port. TCPServer's default initializer calls our override.
        ThreadingHTTPServer.server_close(server)
        raise
    server.daemon_threads = True
    application.shutdown = server.shutdown
    application.previews.start(server.server_address[1])
    application.runtimes.parent_port = server.server_address[1]
    if application.autocapture:
        application.observer.start()
    return server


def serve(repo, port=8731, example=False):
    engine = Engine(repo)
    engine.status()  # fail clearly if the repository was not initialized
    application = Application(engine, Example(engine) if example else None)
    server = make_server(application, port)
    address = f"http://127.0.0.1:{server.server_address[1]}/#token={application.token}"
    print(f"Workgraph is ready: {address}", flush=True)
    print(
        "Local operator UI. Keep this private URL on this computer. Ctrl+C stops the server.",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
