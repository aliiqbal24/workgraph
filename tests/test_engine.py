from pathlib import Path
import sys
import tempfile
import unittest

from demo import fixture, POLICY, CACHE
from workgraph import WorkgraphError


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="workgraph-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.engine = fixture(self.root)

    def revision(self, filename="policy.py", content=None, intent="work"):
        attempt = self.engine.begin(intent)
        (Path(attempt["workspace"]) / filename).write_text(content or POLICY.replace("False", "True"))
        revision = self.engine.snapshot(attempt["attempt"], intent)
        return attempt, revision["revision"]

    def assert_error(self, code, function, *args):
        with self.assertRaises(WorkgraphError) as raised:
            function(*args)
        self.assertEqual(raised.exception.code, code)

    def test_individually_passing_changes_fail_in_composition(self):
        _, auth = self.revision()
        _, cache = self.revision("cache.py", CACHE.replace("False", "True"), "cache")
        for revision in [auth, cache]:
            candidate = self.engine.compose([revision])
            self.assertTrue(self.engine.verify(candidate["candidate"], "privacy")["passed"])
        candidate = self.engine.compose([auth, cache])
        self.assertIsNone(candidate["conflict"])
        self.assertFalse(self.engine.verify(candidate["candidate"], "privacy")["passed"])
        self.assert_error("NOT_READY", self.engine.land, candidate["candidate"])

    def test_evidence_is_not_reused_for_new_candidate(self):
        _, revision = self.revision()
        first = self.engine.compose([revision])["candidate"]
        self.engine.verify(first, "privacy")
        second = self.engine.compose([revision])
        self.assertEqual(self.engine.inspect(first)["state"], "ready")
        self.assertEqual(second["checks"]["privacy"], "untested")

    def test_changed_check_invalidates_passing_evidence(self):
        _, revision = self.revision()
        candidate = self.engine.compose([revision])["candidate"]
        self.engine.verify(candidate, "privacy")
        self.engine.set_check("privacy", [sys.executable, "-c", "raise SystemExit(1)"])
        self.assertEqual(self.engine.inspect(candidate)["checks"]["privacy"], "stale")
        self.assert_error("NOT_READY", self.engine.land, candidate)

    def test_advancing_target_invalidates_other_candidates(self):
        _, revision = self.revision()
        first = self.engine.compose([revision])["candidate"]
        second = self.engine.compose([revision])["candidate"]
        self.engine.verify(first, "privacy")
        self.engine.verify(second, "privacy")
        self.engine.land(first)
        self.assertEqual(self.engine.inspect(second)["state"], "stale")
        self.assert_error("NOT_READY", self.engine.land, second)
        self.assertEqual(self.engine.land(first)["state"], "landed")

    def test_fork_is_an_alternative_and_preserves_old_snapshot(self):
        attempt, revision = self.revision()
        fork = self.engine.begin("alternative", from_revision=revision)
        self.assertEqual(attempt["work"], fork["work"])
        self.assertEqual((Path(fork["workspace"]) / "policy.py").read_text(), POLICY.replace("False", "True"))
        (Path(fork["workspace"]) / "policy.py").write_text(POLICY)
        newer = self.engine.snapshot(fork["attempt"], "different approach")["revision"]
        self.assert_error("ALTERNATIVES", self.engine.compose, [revision, newer])
        old = self.engine.compose([revision])["candidate"]
        self.assertTrue(self.engine.verify(old, "privacy")["passed"])

    def test_conflicting_text_is_a_durable_candidate(self):
        _, one = self.revision(content="REQUIRE_OWNER = True\n", intent="one")
        _, two = self.revision(content="REQUIRE_OWNER = None\n", intent="two")
        candidate = self.engine.compose([one, two])
        self.assertEqual(candidate["state"], "conflicted")
        self.assertIn("policy.py", candidate["conflict"])
        self.assertEqual(self.engine.inspect(candidate["candidate"])["state"], "conflicted")
        self.assert_error("CONFLICTED", self.engine.verify, candidate["candidate"], "privacy")

    def test_checks_cannot_modify_candidate_and_claim_success(self):
        _, revision = self.revision()
        self.engine.set_check("privacy", [sys.executable, "-c", "open('policy.py','w').write('changed')"])
        candidate = self.engine.compose([revision])["candidate"]
        result = self.engine.verify(candidate, "privacy")
        self.assertFalse(result["passed"])
        self.assertIn("modified source", result["output"])

    def test_landing_preserves_user_checkout_and_index(self):
        initial = self.engine.git("rev-parse", "HEAD")
        # Also preserve an unrelated staged edit in the user's working copy.
        (self.root / "notes.txt").write_text("user work\n")
        self.engine.git("add", "notes.txt")
        index = self.engine.git("write-tree")
        _, revision = self.revision()
        candidate = self.engine.compose([revision])["candidate"]
        self.engine.verify(candidate, "privacy")
        self.engine.land(candidate)
        self.assertEqual(self.engine.git("rev-parse", "HEAD"), initial)
        self.assertEqual(self.engine.git("write-tree"), index)
        self.assertEqual((self.root / "notes.txt").read_text(), "user work\n")

    def test_export_has_one_commit_without_experimental_ancestry(self):
        base = self.engine.target()
        attempt, revision = self.revision()
        (Path(attempt["workspace"]) / "new.txt").write_text("another checkpoint")
        revision = self.engine.snapshot(attempt["attempt"], "second checkpoint")["revision"]
        candidate = self.engine.compose([revision])["candidate"]
        self.engine.verify(candidate, "privacy")
        self.engine.land(candidate)
        self.assertEqual(self.engine.git("rev-list", "--count", f"{base}..{self.engine.TARGET}").strip(), "1")

    def test_resume_returns_context_and_detects_unsaved_work(self):
        attempt, revision = self.revision()
        resumed = self.engine.resume(attempt["attempt"])
        self.assertEqual(resumed["revision"], revision)
        self.assertEqual(resumed["intent"], "work")
        self.assertFalse(resumed["unsaved_changes"])
        (Path(attempt["workspace"]) / "new.txt").write_text("in progress")
        self.assertTrue(self.engine.resume(attempt["attempt"])["unsaved_changes"])


if __name__ == "__main__":
    unittest.main()
