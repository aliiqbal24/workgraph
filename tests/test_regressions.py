import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

import test_engine
from workgraph import WorkgraphError
from workgraph.api import Router
from workgraph.hermes_adapter import HermesAdapter


class RegressionTests(unittest.TestCase):
    setUp = test_engine.EngineTests.setUp
    revision = test_engine.EngineTests.revision
    assert_error = test_engine.EngineTests.assert_error

    def test_superseded_attempt_cannot_be_reconciled_or_resurrected(self):
        attempt, _ = self.revision()
        self.engine.takeover(attempt["attempt"], "replacement")
        self.assert_error("ATTEMPT_INACTIVE", self.engine.reconcile, attempt["attempt"], "intruder")
        self.assert_error("ATTEMPT_INACTIVE", self.engine.transition, attempt["attempt"], "active")

    def test_conflicting_transitive_dependency_is_rejected(self):
        first, a1 = self.revision("api.py", "version = 1\n", "API")
        client = self.engine.begin("client", depends_on=[a1])
        (Path(client["workspace"]) / "client.py").write_text("api_version = 1\n")
        b1 = self.engine.snapshot(client["attempt"], "Client version one")["revision"]
        alternative = self.engine.begin("API", work_id=first["work"], depends_on=[b1])
        (Path(alternative["workspace"]) / "api.py").write_text("version = 2\n")
        a2 = self.engine.checkpoint(alternative["attempt"], "API version two", select=True)["revision"]
        self.assert_error("DEPENDENCY_MISMATCH", self.engine.compose, [a2])

    def test_unchanged_checkpoint_can_explicitly_select_revision(self):
        attempt, first = self.revision()
        alternative = self.engine.begin("alternative", from_revision=first)
        (Path(alternative["workspace"]) / "other.txt").write_text("alternative\n")
        second = self.engine.checkpoint(alternative["attempt"], "alternative", select=True)["revision"]
        self.assertEqual(self.engine.status()["work"][0]["selected_revision"], second)
        self.engine.checkpoint(attempt["attempt"], "work", select=True)
        self.assertEqual(self.engine.status()["work"][0]["selected_revision"], first)

    def test_aborted_compare_and_swap_replays_failure(self):
        _, revision = self.revision()
        candidate = self.engine.compose([revision])["candidate"]
        self.engine.verify(candidate, "privacy")
        real = self.engine.git
        def fail(*args, **kwargs):
            if args[:2] == ("update-ref", self.engine.TARGET):
                return subprocess.CompletedProcess([], 1, "", "simulated concurrent update")
            return real(*args, **kwargs)
        self.engine.git = fail
        self.assert_error("STALE_BASE", self.engine.land, candidate, "same-cas")
        self.engine.git = real
        self.assert_error("STALE_BASE", self.engine.land, candidate, "same-cas")

    def test_interrupted_acceptance_is_recovered_before_a_later_acceptance(self):
        _, revision = self.revision()
        first = self.engine.compose([revision])["candidate"]
        self.engine.verify(first, "privacy")
        real = self.engine.git
        def crash(*args, **kwargs):
            result = real(*args, **kwargs)
            if args[:2] == ("update-ref", self.engine.TARGET):
                raise RuntimeError("simulated crash")
            return result
        self.engine.git = crash
        with self.assertRaises(RuntimeError):
            self.engine.land(first, "crash-once")
        self.engine.git = real
        _, newer = self.revision("unrelated.txt", "another change\n", "unrelated")
        second = self.engine.compose([newer])["candidate"]
        self.engine.verify(second, "privacy")
        self.engine.land(second)
        self.assertEqual(self.engine.inspect(first)["state"], "landed")
        self.assertEqual(self.engine.land(first, "crash-once")["state"], "landed")

    def test_missing_sandbox_never_runs_verification_on_the_host(self):
        _, revision = self.revision()
        candidate = self.engine.compose([revision])["candidate"]
        with patch.dict("os.environ", {}, clear=True), patch("workgraph.core.shutil.which", return_value=None):
            self.assert_error("SANDBOX_REQUIRED", self.engine.verify, candidate, "privacy")

    def test_runtime_resume_binds_only_the_owner(self):
        attempt = self.engine.begin("own work", session="owner")
        router = Router(self.root, "owner")
        router.call({"action": "resume", "attempt": attempt["attempt"]})
        self.assertEqual(router.attempt, attempt["attempt"])
        stranger = Router(self.root, "stranger")
        stranger.call({"action": "resume", "attempt": attempt["attempt"]})
        self.assertIsNone(stranger.attempt)

    def test_duplicate_native_tool_ids_do_not_repeat_side_effects(self):
        adapter = HermesAdapter(self.root)
        opened = json.loads(adapter.tool({"action": "open", "intent": "capture"}, session_id="host-session"))
        path = Path(opened["workspace"]) / "append.txt"
        count = []
        def execute(args):
            count.append(1)
            with path.open("a") as file:
                file.write("one\n")
            return json.dumps({"success": True})
        args = {"path": str(path), "content": "one\n"}
        first = json.loads(adapter.execute("write_file", args, execute, session_id="host-session", tool_call_id="same-call"))
        second = json.loads(adapter.execute("write_file", args, execute, session_id="host-session", tool_call_id="same-call"))
        self.assertEqual(len(count), 1)
        self.assertEqual(first["workgraph"]["checkpoint"], second["workgraph"]["checkpoint"])
        self.assertFalse(self.engine.resume(opened["attempt"])["unsaved_changes"])

    def test_search_and_terminal_routing_fail_closed(self):
        adapter = HermesAdapter(self.root)
        opened = json.loads(adapter.tool({"action": "open", "intent": "route"}, session_id="host-session"))
        revised = adapter.request("search_files", {"path": ".", "pattern": "route"}, session_id="host-session")["args"]
        self.assertEqual(revised["path"], opened["workspace"])
        self.assertIsNone(adapter.guard("search_files", revised, session_id="host-session"))
        self.assertEqual(adapter.guard("write_file", {"path": "not-routed.txt"}, session_id="host-session")["action"], "block")
        terminal = {"workdir": opened["workspace"], "command": "echo no"}
        self.assertEqual(adapter.guard("terminal", terminal, session_id="host-session")["action"], "block")

    def test_acceptance_retains_the_exact_evidence_basis(self):
        _, revision = self.revision()
        candidate = self.engine.compose([revision])["candidate"]
        evidence = self.engine.verify(candidate, "privacy")["evidence"]
        self.engine.land(candidate)
        self.engine.set_check("privacy", [sys.executable, "-c", "raise SystemExit(1)"])
        accepted = self.engine.inspect(candidate)
        self.assertEqual(accepted["state"], "landed")
        self.assertEqual(accepted["acceptance"]["basis"]["evidence"][0]["evidence"], evidence)


if __name__ == "__main__":
    unittest.main()
