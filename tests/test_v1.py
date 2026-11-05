from pathlib import Path
import sys
import threading
import time
import unittest

from demo import POLICY
import test_engine
from workgraph import WorkgraphError


class V1Tests(unittest.TestCase):
    setUp = test_engine.EngineTests.setUp
    revision = test_engine.EngineTests.revision
    assert_error = test_engine.EngineTests.assert_error
    def test_request_id_replays_without_duplicate_work(self):
        one = self.engine.begin("one task", request_id="request-123")
        two = self.engine.begin("one task", request_id="request-123")
        self.assertEqual(one, two)
        self.assertEqual(len(self.engine.status()["work"]), 1)
        self.assert_error("REQUEST_REUSED", self.engine.begin, "different task", "local", None, None,
                          "local", None, None, "request-123")

    def test_context_and_ownership_survive_takeover(self):
        attempt = self.engine.begin("finish migration", session="hermes-1", runtime="hermes")
        (Path(attempt["workspace"]) / "migration.py").write_text("phase = 1\n")
        revision = self.engine.checkpoint(attempt["attempt"], "Migration half complete",
            plan=["Update the client"], questions=["Does the old response need a compatibility alias?"],
            decisions=["Keep old clients working"], session="hermes-1")
        taken = self.engine.takeover(attempt["attempt"], "codex-2", "codex")
        self.assertNotEqual(taken["workspace"], attempt["workspace"])
        self.assertEqual(self.engine.resume(taken["attempt"])["context"]["questions"],
                         ["Does the old response need a compatibility alias?"])
        self.assertEqual((Path(taken["workspace"]) / "migration.py").read_text(), "phase = 1\n")
        self.assert_error("ATTEMPT_INACTIVE", self.engine.checkpoint, attempt["attempt"], "old worker")
        self.assert_error("WRONG_OWNER", self.engine.checkpoint, taken["attempt"], "wrong", None, None, None, "hermes-1")
        (Path(taken["workspace"]) / "migration.py").write_text("phase = 2\n")
        newer = self.engine.checkpoint(taken["attempt"], "Migration complete", session="codex-2")
        self.assertEqual(self.engine.status()["work"][0]["selected_revision"], newer["revision"])
        # A late old worker can change only its abandoned copy, not the new owner's.
        (Path(attempt["workspace"]) / "migration.py").write_text("late old write\n")
        self.assertEqual((Path(taken["workspace"]) / "migration.py").read_text(), "phase = 2\n")

    def test_dependencies_are_exact_and_outdated_work_is_preserved(self):
        source, first = self.revision("api.py", "FIELD = 'name'\n", "API response")
        client = self.engine.begin("client", depends_on=[first])
        self.assertEqual((Path(client["workspace"]) / "api.py").read_text(), "FIELD = 'name'\n")
        (Path(client["workspace"]) / "client.py").write_text("field = 'name'\n")
        client_revision = self.engine.snapshot(client["attempt"], "Client uses name")["revision"]
        (Path(source["workspace"]) / "api.py").write_text("FIELD = 'display_name'\n")
        second = self.engine.snapshot(source["attempt"], "API now uses display_name")["revision"]
        resumed = self.engine.resume(client["attempt"])
        self.assertEqual(resumed["outdated_dependencies"][0]["current"], second)
        self.assertEqual(resumed["outdated_dependencies"][0]["pinned"], first)
        candidate = self.engine.compose([client_revision])
        self.assertEqual(candidate["state"], "stale")
        self.assert_error("NOT_READY", self.engine.land, candidate["candidate"])
        self.assert_error("DEPENDENCY_MISMATCH", self.engine.compose, [second, client_revision])
        self.assertEqual((Path(client["workspace"]) / "client.py").read_text(), "field = 'name'\n")

    def test_reconciliation_keeps_own_edits_and_updates_dependency(self):
        source, first = self.revision("api.py", "FIELD = 'name'\n", "API response")
        client = self.engine.begin("client", depends_on=[first])
        (Path(client["workspace"]) / "client.py").write_text("field = 'name'\n")
        self.engine.snapshot(client["attempt"], "Client added")
        (Path(source["workspace"]) / "api.py").write_text("FIELD = 'display_name'\n")
        second = self.engine.snapshot(source["attempt"], "API updated")["revision"]
        new = self.engine.reconcile(client["attempt"])
        self.assertEqual((Path(new["workspace"]) / "client.py").read_text(), "field = 'name'\n")
        self.assertEqual((Path(new["workspace"]) / "api.py").read_text(), "FIELD = 'display_name'\n")
        revision = self.engine.checkpoint(new["attempt"], "Client reconciled", select=True)
        candidate = self.engine.compose([revision["revision"]])
        self.assertIn(second, candidate["manifest"].values())
        self.assertEqual(candidate["state"], "unverified")

    def test_trusted_check_source_is_frozen(self):
        check = self.root / "contract.py"
        check.write_text("raise SystemExit(1)\n")
        self.engine.set_check("privacy", [sys.executable, "{check_root}/contract.py"], trusted_files=[check])
        check.write_text("print('weakened locally')\n")
        _, revision = self.revision()
        candidate = self.engine.compose([revision])["candidate"]
        self.assertFalse(self.engine.verify(candidate, "privacy")["passed"])

    def test_acceptance_journal_recovers_after_git_ref_write(self):
        _, revision = self.revision()
        candidate = self.engine.compose([revision])["candidate"]
        self.engine.verify(candidate, "privacy")
        real_git = self.engine.git

        def crash(*args, **kwargs):
            result = real_git(*args, **kwargs)
            if args[:2] == ("update-ref", self.engine.TARGET):
                raise RuntimeError("simulated process failure after atomic ref update")
            return result
        self.engine.git = crash
        with self.assertRaises(RuntimeError):
            self.engine.land(candidate, request_id="accept-once")
        self.engine.git = real_git
        recovered = self.engine.recover()
        self.assertEqual(recovered["landings"][0]["state"], "done")
        self.assertEqual(self.engine.land(candidate, request_id="accept-once")["state"], "landed")

    def test_check_timeout_is_a_failed_observation(self):
        self.engine.set_check("privacy", [sys.executable, "-c", "import time; time.sleep(30)"])
        _, revision = self.revision()
        candidate = self.engine.compose([revision])["candidate"]
        result = self.engine.verify(candidate, "privacy", timeout=0.05)
        self.assertFalse(result["passed"])
        self.assertIn("timed out", result["output"])

    def test_other_work_can_progress_while_a_check_runs(self):
        self.engine.set_check("privacy", [sys.executable, "-c", "import time; time.sleep(.3)"])
        _, revision = self.revision()
        candidate = self.engine.compose([revision])["candidate"]
        errors = []
        def run():
            try:
                self.engine.verify(candidate, "privacy")
            except Exception as error:
                errors.append(error)
        thread = threading.Thread(target=run)
        thread.start()
        time.sleep(.06)
        started = time.monotonic()
        self.engine.begin("independent work")
        self.assertLess(time.monotonic() - started, .25)
        thread.join()
        self.assertFalse(errors)


if __name__ == "__main__":
    unittest.main()
