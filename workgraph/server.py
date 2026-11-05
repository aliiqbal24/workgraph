"""Loopback-only operator UI. Bearer authentication and strict browser origins."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import secrets
import threading
from urllib.parse import urlparse

from .engine import Engine, WorkgraphError
from .example import Example


class Application:
    def __init__(self, engine, example=None):
        self.engine = engine
        self.example = example
        self.token = secrets.token_urlsafe(32)
        self.assets = Path(__file__).parent / "web"

    def dispatch(self, args):
        action = args.get("action")
        key = args.get("request_id")
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

        def send(self, code, data, content_type="application/json; charset=utf-8"):
            body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

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
            if route == "/api/state":
                if not self.authorized():
                    return
                result = application.engine.status()
                result["example"] = application.example.state() if application.example else None
                return self.send(200, result)
            files = {"/": ("index.html", "text/html; charset=utf-8"),
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

    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
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
