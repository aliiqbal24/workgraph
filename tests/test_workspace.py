"""Opening is observational; editing capabilities never enter agent responses."""

import json
from pathlib import Path
import tempfile
import threading
import unittest
import io
import base64
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from workgraph.playground import Playground
from workgraph.server import Application, make_server
from workgraph.api import Router
from workgraph.mcp import serve
from workgraph.errors import WorkgraphError
from workgraph.behaviors import Behaviors


class WorkspaceTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.engine = Playground.create(Path(self.directory.name) / "project")
        self.app = Application(self.engine, capture=False)
        self.server = make_server(self.app, 0)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = "http://127.0.0.1:" + str(self.server.server_address[1])

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.directory.cleanup()

    def request(self, route, token, body=None, headers=None):
        request = Request(
            self.base + route,
            data=json.dumps(body).encode() if body else None,
            headers={
                "Authorization": "Bearer " + token,
                **({"Content-Type": "application/json"} if body else {}),
                **(headers or {}),
            },
        )
        with urlopen(request, timeout=5) as response:
            return json.load(response)

    def test_viewer_can_inspect_but_cannot_mutate_or_obtain_operator_token(self):
        value = self.request("/api/studio", self.app.viewer)
        self.assertFalse(value["operator"])
        self.assertNotIn(self.app.token, json.dumps(value))
        before = len(value["versions"])
        chosen = value["current"]
        for action in (
            "studio.choose",
            "studio.branch",
            "behavior.protect",
            "studio.focus",
            "runtime.open",
            "app.configure",
            "studio.agent",
        ):
            with self.assertRaises(HTTPError) as error:
                self.request(
                    "/api/action",
                    self.app.viewer,
                    {"action": action, "revision": chosen, "name": "unapproved"},
                )
            self.assertEqual(error.exception.code, 403)
            error.exception.close()
        self.assertEqual(len(self.app.studio.history()["versions"]), before)

    def test_browser_focus_is_persistent_and_does_not_choose_or_rewrite_files(self):
        history = self.app.studio.history()
        chosen = history["current"]
        other = next(v["id"] for v in history["versions"] if v["id"] != chosen)
        index = self.engine.git("write-tree")
        files = {p: p.read_bytes() for p in self.engine.repo.glob("*") if p.is_file()}
        camera = {"x": 123.5, "y": -500, "z": 0.8}
        self.request(
            "/api/action",
            self.app.token,
            {"action": "studio.focus", "revision": other, "camera": camera},
        )
        self.assertEqual(
            self.app.studio.history()["focus"], {"revision": other, "camera": camera}
        )
        self.assertEqual(self.app.studio.history()["current"], chosen)
        self.assertEqual(self.engine.git("write-tree"), index)
        self.assertTrue(
            all(path.read_bytes() == content for path, content in files.items())
        )
        self.assertEqual(
            len(self.app.studio.history()["versions"]), len(history["versions"])
        )

    def test_host_and_cross_origin_requests_cannot_use_even_a_valid_bearer(self):
        for headers in (
            {"Origin": "http://attacker.invalid"},
            {"Host": "attacker.invalid"},
        ):
            with self.assertRaises(HTTPError) as error:
                self.request("/api/studio", self.app.token, headers=headers)
            self.assertEqual(error.exception.code, 403)
            error.exception.close()

    def test_busy_port_retry_keeps_the_controller_and_capture_service_usable(self):
        engine = Playground.create(Path(self.directory.name) / "another-project")
        app = Application(engine, capture=False, autocapture=False)
        with self.assertRaises(OSError):
            make_server(app, self.server.server_address[1])
        self.assertTrue(app.jobs.owns_controller)
        self.assertFalse(app.closing)
        replacement = make_server(app, 0)
        try:
            self.assertTrue(app.studio_state()["versions"])
        finally:
            replacement.server_close()

    def test_workspace_tool_does_not_create_attempt_or_return_operator_capability(self):
        before = self.engine.status()
        router = Router(self.engine.repo)
        with patch(
            "workgraph.workspace.open_workspace",
            return_value={"url": self.base + "/#view=viewer", "opened": True},
        ) as opening:
            result = router.call({"action": "workspace"})
        opening.assert_called_once_with(self.engine.repo)
        self.assertIsNone(router.attempt)
        self.assertEqual(before, self.engine.status())
        self.assertNotIn(self.app.token, json.dumps(result))

    def test_portable_server_can_start_outside_git_and_select_a_project_explicitly(
        self,
    ):
        router = Router("/tmp", unbound=True)
        with self.assertRaises(WorkgraphError):
            router.call({"action": "history"})
        result = router.call({"action": "history", "repository": str(self.engine.repo)})
        self.assertEqual(result["repository"], str(self.engine.repo))
        self.assertIsNone(router.attempt)

    def test_behavior_definitions_inherit_without_model_write_access(self):
        history = self.app.studio.history()
        base = history["versions"][0]["id"]
        flow = self.app.behaviors.create(
            base,
            "Heading stays visible",
            {
                "steps": [
                    {
                        "action": "expect",
                        "locator": {"type": "css", "value": "h1"},
                        "text": "Luma",
                    }
                ]
            },
        )
        descendant = history["versions"][-1]["id"]
        self.assertIn(
            flow["id"], [f["id"] for f in self.app.behaviors.list(descendant)]
        )
        visible = Router(self.engine.repo).call({"action": "history"})
        self.assertEqual(
            next(v for v in visible["versions"] if v["id"] == descendant)["protection"][
                "total"
            ],
            1,
        )
        with self.assertRaises(WorkgraphError):
            Router(self.engine.repo).call(
                {"action": "behavior.protect", "revision": base}
            )
        with self.assertRaises(WorkgraphError):
            self.app.behaviors.create(
                base,
                "No expectation",
                {
                    "steps": [
                        {
                            "action": "click",
                            "locator": {"type": "css", "value": "button"},
                        }
                    ]
                },
            )

    def test_readonly_mcp_look_returns_an_image_block_without_changing_history(self):
        revision = self.app.studio.history()["current"]
        before = self.engine.status()
        content = base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
        )
        fixture = Path(self.directory.name) / "fixture.png"
        fixture.write_bytes(content)
        key = self.app.artifacts.import_media(fixture)
        manifest = {
            "images": [
                {
                    "name": "Protocol fixture",
                    "file": key,
                    "thumb": key,
                    "width": 1,
                    "height": 1,
                }
            ]
        }
        with self.engine.db() as db:
            db.execute(
                "INSERT INTO product_artifacts VALUES (?,?,'ready',?,NULL,0)",
                (revision, "protocol-fixture", json.dumps(manifest)),
            )
        request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": "workgraph_read",
                "arguments": {"action": "look", "revision": revision},
            },
        }
        out = io.StringIO()
        serve(
            self.engine.repo, stdin=io.StringIO(json.dumps(request) + "\n"), stdout=out
        )
        result = json.loads(out.getvalue())["result"]
        self.assertFalse(result["isError"])
        image = result["content"][1]
        self.assertEqual(image["type"], "image")
        self.assertEqual(image["mimeType"], "image/png")
        self.assertEqual(base64.b64decode(image["data"]), content)
        self.assertEqual(self.engine.status(), before)


if __name__ == "__main__":
    unittest.main()
