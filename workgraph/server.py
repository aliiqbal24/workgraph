"""Loopback-only operator UI. Bearer authentication and strict browser origins."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import urlparse,parse_qs

from .engine import Engine, WorkgraphError
from .example import Example
from .studio import Studio
from .preview import Previews
from .jobs import Jobs
import shutil


class Application:
    def __init__(self, engine, example=None):
        self.engine = engine
        self.example = example
        self.token = secrets.token_urlsafe(32)
        self.assets = Path(__file__).parent / "web"
        self.studio = Studio(engine)
        self.previews = Previews(self.studio)
        self.jobs = Jobs(self.studio)

    def close(self):
        self.jobs.close()
        self.previews.close()

    def studio_state(self):
        result = self.studio.history()
        result["preview_base"] = self.previews.base
        result["runtimes"] = {name:bool(shutil.which(name)) for name in ("hermes","codex","claude")}
        return result

    def dispatch(self, args):
        action = args.get("action")
        key = args.get("request_id")
        if action == "studio.start":
            return self.studio.start(args.get("name","Starting point"), key)
        if action == "studio.branch":
            return self.studio.branch(args["revision"],args["name"],runtime=args.get("runtime","local"),prompt=args.get("prompt"),request_id=key)
        if action == "studio.note":
            return self.studio.note(args["revision"],args.get("label"),args.get("starred"),key)
        if action == "studio.choose":
            return self.studio.choose(args["revision"],key)
        if action == "studio.compare":
            return self.studio.compare(args["left"],args["right"])
        if action == "studio.combine":
            return self.studio.combine(args["target"],args["source"],args["paths"],args.get("name","Combined direction"),key)
        if action == "studio.agent":
            reuse=args.get("reuse_path",False)
            if not isinstance(reuse,bool):raise WorkgraphError("INVALID_ARGUMENTS","Choose whether to continue this path or create another.")
            return self.jobs.start(args["revision"],args["name"],args["runtime"],args["prompt"],key,reuse_path=reuse)
        if action == "studio.cancel":
            return self.jobs.cancel(args["job"])
        if action == "studio.file":
            content=self.studio.read(args["revision"],args["path"],limit=1000000)
            return {"path":args["path"],"content":content.decode("utf-8",errors="replace")}
        if action == "studio.files":
            return {"revision":args["revision"],"files":list(self.studio.files(args["revision"]))}
        if action == "open":
            return self.engine.begin(args.get("intent", ""), session=args.get("session", "operator"),
                                     runtime=args.get("runtime", "local"), depends_on=args.get("depends_on", []), request_id=key)
        if action == "checkpoint":
            return self.engine.checkpoint(args["attempt"], summary=args.get("summary"),
                plan=args.get("plan"), decisions=args.get("decisions"), questions=args.get("questions"), request_id=key)
        if action == "resume":
            return self.engine.resume(args["attempt"])
        if action == "takeover":
            return self.engine.takeover(args["attempt"], args.get("session", "replacement"), args.get("runtime", "local"), key)
        if action == "transition":
            return self.engine.transition(args["attempt"], args["state"], request_id=key)
        if action == "fork":
            return self.engine.begin("Alternative approach", session=args.get("session", "alternative"),
                runtime=args.get("runtime", "local"), from_revision=args["revision"], request_id=key)
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

        def send(self, code, data, content_type="application/json; charset=utf-8",download=None):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            if download:self.send_header("Content-Disposition",f'attachment; filename="{download}"')
            preview = (application.previews.base or "").split("/",3)[:3]
            origin = "/".join(preview) if preview else "'none'"
            self.send_header("Content-Security-Policy", f"default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; frame-src {origin}; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass

        def authorized(self):
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
            if not secrets.compare_digest(value, "Bearer " + application.token):
                self.send(401, {"error": "UNAUTHORIZED", "message": "Open the private URL printed by workgraph serve."})
                return False
            return True

        def do_GET(self):
            route = urlparse(self.path).path
            if route=="/api/export":
                if not self.authorized():return
                revision=parse_qs(urlparse(self.path).query).get("revision",[""])[0]
                try:
                    content=application.studio.archive(revision)
                    return self.send(200,content,"application/zip",download="workgraph-"+revision[-8:]+".zip")
                except WorkgraphError as error:return self.send(409,error.as_dict())
            if route == "/favicon.ico":
                return self.send(204,b"","image/x-icon")
            if route == "/api/studio":
                if not self.authorized():
                    return
                return self.send(200,application.studio_state())
            if route == "/api/state":
                if not self.authorized():
                    return
                result = application.engine.status()
                result["example"] = application.example.state() if application.example else None
                return self.send(200, result)
            files = {"/": ("studio.html", "text/html; charset=utf-8"),
                     "/engineering": ("index.html", "text/html; charset=utf-8"),
                     "/studio.js": ("studio.js", "text/javascript; charset=utf-8"),
                     "/studio.css": ("studio.css", "text/css; charset=utf-8"),
                     "/app.js": ("app.js", "text/javascript; charset=utf-8"),
                     "/style.css": ("style.css", "text/css; charset=utf-8")}
            if route not in files:
                return self.send(404, {"error": "NOT_FOUND"})
            name, mime = files[route]
            self.send(200, (application.assets / name).read_bytes(), mime)

        def do_POST(self):
            if not self.authorized():
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
                self.send(400, {"error": "INVALID_ARGUMENTS", "message": "The request is missing a required field or contains an invalid value."})
            except Exception as error:
                self.send(500, {"error": "OPERATION_FAILED", "message": f"The operation did not complete ({type(error).__name__}). Inspect workgraph doctor."})

    class Server(ThreadingHTTPServer):
        def server_close(self):
            application.close()
            super().server_close()
    server = Server(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    application.previews.start(server.server_address[1])
    return server


def serve(repo, port=8731, example=False):
    engine = Engine(repo)
    engine.status()  # fail clearly if the repository was not initialized
    application = Application(engine, Example(engine) if example else None)
    server = make_server(application, port)
    address = f"http://127.0.0.1:{server.server_address[1]}/#token={application.token}"
    print(f"Workgraph is ready: {address}", flush=True)
    print("Local operator UI. Keep this private URL on this computer. Ctrl+C stops the server.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
