import contextlib
import io
import json
from pathlib import Path
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import test_engine
from workgraph.cli import main
from workgraph.mcp import serve
from workgraph.server import Application, make_server


class InterfaceTests(unittest.TestCase):
    setUp = test_engine.EngineTests.setUp

    def test_launch_options_after_runtime_are_parsed(self):
        output = io.StringIO()
        with patch("workgraph.launch.launch", return_value={"ready": True}) as launch, contextlib.redirect_stdout(output):
            self.assertEqual(main(["launch", "codex", "--intent", "new work", "--print", "--", "--json"]), 0)
            self.assertEqual(launch.call_args.args[2], "new work")
            self.assertEqual(launch.call_args.args[4], ["--json"])
            self.assertTrue(launch.call_args.args[5])

    def test_trusted_file_options_after_check_name_are_parsed(self):
        check = self.root / "test-contract.py"
        check.write_text("print('pass')")
        with contextlib.redirect_stdout(io.StringIO()):
            code = main(["--repo", str(self.root), "set-check", "example", "--trusted-file", str(check),
                         "--", "python", "{check_root}/test-contract.py"])
        self.assertEqual(code, 0)
        configured = next(check for check in self.engine.status()["checks"] if check["name"] == "example")
        self.assertEqual(configured["trusted_files"], ["test-contract.py"])

    def test_mcp_protocol_and_operator_boundary(self):
        source = io.StringIO("\n".join(json.dumps(message) for message in [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "workgraph", "arguments": {"action": "land"}}},
        ]) + "\n")
        output = io.StringIO()
        serve(self.root, stdin=source, stdout=output)
        results = [json.loads(line) for line in output.getvalue().splitlines()]
        self.assertEqual(results[0]["result"]["serverInfo"]["name"], "workgraph")
        self.assertEqual(results[1]["result"]["tools"][0]["name"], "workgraph")
        self.assertTrue(results[2]["result"]["isError"])

    def test_http_operator_auth_and_origin(self):
        app = Application(self.engine)
        server = make_server(app, 0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        address = f"http://127.0.0.1:{server.server_address[1]}"
        try:
            with self.assertRaises(HTTPError) as denied:
                urlopen(address + "/api/state")
            self.assertEqual(denied.exception.code, 401)
            denied.exception.close()
            request = Request(address + "/api/state", headers={"Authorization": "Bearer " + app.token})
            self.assertEqual(json.load(urlopen(request))["version"], "1.0.0")
            request = Request(address + "/api/action", data=b'{"action":"open","intent":"bad origin"}',
                headers={"Authorization": "Bearer " + app.token, "Origin": "https://unrelated.invalid", "Content-Type": "application/json"})
            with self.assertRaises(HTTPError) as denied:
                urlopen(request)
            self.assertEqual(denied.exception.code, 403)
            denied.exception.close()
            self.assertEqual(len(self.engine.status()["work"]), 0)
        finally:
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    unittest.main()
