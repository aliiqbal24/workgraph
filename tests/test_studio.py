"""User-story invariants: old versions, isolated directions and explicit combination."""
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import contextlib

from workgraph.engine import WorkgraphError
from workgraph.playground import Playground
from workgraph.studio import Studio
from workgraph.jobs import Jobs
from workgraph.api import Router
from workgraph.cli import main


class StudioTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix="workgraph-explore-");self.addCleanup(self.temp.cleanup)
        self.engine=Playground.create(Path(self.temp.name)/"project")
        self.studio=Studio(self.engine)
        self.refs=json.loads((self.engine.home/"playground.json").read_text())

    def test_choose_older_version_preserves_later_work_and_user_checkout(self):
        before=self.engine.git("rev-parse","HEAD");index=self.engine.git("write-tree")
        self.studio.choose(self.refs["first"])
        state=Studio(self.engine).history()
        self.assertEqual(state["current"],self.refs["first"])
        self.assertIn(self.refs["busy"],[v["id"] for v in state["versions"]])
        self.assertEqual(before,self.engine.git("rev-parse","HEAD"))
        self.assertEqual(index,self.engine.git("write-tree"))

    def test_paths_fork_exact_point_and_retry_does_not_duplicate(self):
        one=self.studio.branch(self.refs["warm"],"Another idea",request_id="same-path")
        two=self.studio.branch(self.refs["warm"],"Another idea",request_id="same-path")
        self.assertEqual(one,two)
        self.assertEqual(self.studio.revision(one["revision"])["parent"],self.refs["warm"])
        original=self.studio.read(self.refs["warm"],"components/hero.js")
        (Path(one["workspace"])/"components/hero.js").write_text("a different direction")
        self.assertEqual(self.studio.read(self.refs["warm"],"components/hero.js"),original)
        self.assertNotEqual(self.studio.history()["current"],one["revision"])

    def test_combination_takes_only_selected_files_and_retains_sources(self):
        left,right=self.refs["warm"],self.refs["playful"]
        result=self.studio.combine(left,right,["components/navigation.js"],"Best of both",request_id="combine-once")
        self.assertEqual(self.studio.combine(left,right,["components/navigation.js"],"Best of both",request_id="combine-once"),result)
        self.assertEqual(self.studio.read(result["revision"],"components/navigation.js"),self.studio.read(right,"components/navigation.js"))
        self.assertEqual(self.studio.read(result["revision"],"components/hero.js"),self.studio.read(left,"components/hero.js"))
        state=self.studio.history();v=next(v for v in state["versions"] if v["id"]==result["revision"])
        self.assertEqual(v["source"],{"revision":right,"paths":["components/navigation.js"]})
        self.assertIn(left,[v["id"] for v in state["versions"]]);self.assertIn(right,[v["id"] for v in state["versions"]])
        self.assertEqual(state["current"],left)

    def test_combination_supports_explicit_deletion(self):
        path=self.studio.branch(self.refs["warm"],"No footer")
        (Path(path["workspace"])/"components/footer.js").unlink()
        source=self.engine.checkpoint(path["attempt"],"Removed footer",select=False)["revision"]
        result=self.studio.combine(self.refs["warm"],source,["components/footer.js"],"Selected deletion")
        self.assertNotIn("components/footer.js",self.studio.files(result["revision"]))
        self.assertIn("components/footer.js",self.studio.files(self.refs["warm"]))

    def test_preview_and_transfer_refuse_metadata_symlinks_and_traversal(self):
        outside=Path(self.temp.name)/"outside-fixture.txt"
        outside.write_text("fixture data that must remain outside the saved project")
        for path in ("../private",".git/config",str(outside),"components/../../bad"):
            with self.assertRaises(WorkgraphError):self.studio.read(self.refs["warm"],path)
        branch=self.studio.branch(self.refs["warm"],"A link")
        (Path(branch["workspace"])/"outside").symlink_to(outside)
        saved=self.engine.checkpoint(branch["attempt"],"Link",select=False)["revision"]
        self.assertNotIn("outside",self.studio.files(saved))
        with self.assertRaises(WorkgraphError):self.studio.combine(self.refs["warm"],saved,["outside"],"No link")

    def test_names_and_stars_do_not_rewrite_immutable_context(self):
        original=self.studio.revision(self.refs["warm"])
        self.studio.note(self.refs["warm"],label="The one I love",starred=True)
        self.assertEqual(original,self.studio.revision(self.refs["warm"]))
        v=next(v for v in self.studio.history()["versions"] if v["id"]==self.refs["warm"])
        self.assertEqual(v["title"],"The one I love");self.assertTrue(v["starred"])

    def test_start_captures_current_unstaged_files_without_changing_index(self):
        (self.engine.repo/"new-file.txt").write_text("unsaved source")
        (self.engine.repo/"components/footer.js").unlink()
        index=self.engine.git("write-tree")
        result=self.studio.start("Present working files")
        self.assertEqual(self.studio.read(result["revision"],"new-file.txt"),b"unsaved source")
        self.assertNotIn("components/footer.js",self.studio.files(result["revision"]))
        self.assertEqual(index,self.engine.git("write-tree"))

    def test_agent_can_read_saved_source_and_branch_with_trusted_owner(self):
        router=Router(self.engine.repo,"trusted-test-owner","mcp")
        record=router.call({"action":"version","revision":self.refs["playful"],"file":"components/navigation.js"})
        self.assertIn("Find your favorite",record["content"])
        branch=router.call({"action":"branch","revision":self.refs["warm"],"name":"Agent direction"})
        self.assertEqual(branch["session"],"trusted-test-owner")
        self.assertEqual(router.attempt,branch["attempt"])
        self.assertIn("versions",router.call({"action":"history"}))

    def test_runtime_failures_reach_cli_exit_code(self):
        with patch("workgraph.launch.launch",return_value={"exit_code":7}),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main(["launch","hermes","--attempt","example"]),7)

    def test_agent_job_lifecycle_captures_actual_subprocess_files(self):
        jobs=Jobs(self.studio);self.addCleanup(jobs.close)
        def invocation(attempt,runtime,query):
            return [sys.executable,"-c","from pathlib import Path; Path('job-proof.txt').write_text('real child output'); print('done')"]
        with patch("workgraph.launch.command",return_value=([],Path('.'))),patch("workgraph.jobs.shutil.which",return_value="runtime"),patch.object(jobs,"invocation",side_effect=invocation):
            result=jobs.start(self.refs["warm"],"Subprocess proof","hermes","Write proof",request_id="job-replay")
            for thread in jobs.threads:thread.join(timeout=15)
            state=self.studio.history();job=next(j for j in state["jobs"] if j["id"]==result["job"])
            self.assertEqual(job["state"],"completed",job)
            self.assertEqual(self.engine.resume(result["attempt"])["state"],"paused")
            head=self.engine.resume(result["attempt"])["revision"]
            self.assertEqual(self.studio.read(head,"job-proof.txt"),b"real child output")
            again=jobs.start(self.refs["warm"],"Subprocess proof","hermes","Write proof",request_id="job-replay")
            self.assertEqual(result["job"],again["job"])

    def test_second_window_cannot_interrupt_or_claim_another_controller(self):
        first=Jobs(self.studio);second=Jobs(self.studio)
        try:
            self.assertTrue(first.owns_controller);self.assertFalse(second.owns_controller)
            with self.assertRaises(WorkgraphError):second.start(self.refs["warm"],"Other","hermes","Try")
        finally:second.close();first.close()

    def test_stop_agent_preserves_partial_files_as_a_saved_version(self):
        jobs=Jobs(self.studio);self.addCleanup(jobs.close)
        def invocation(attempt,runtime,query):
            return [sys.executable,"-c","from pathlib import Path; import time; Path('partial.txt').write_text('keep this work'); print('started',flush=True); time.sleep(30)"]
        with patch("workgraph.launch.command",return_value=([],Path('.'))),patch("workgraph.jobs.shutil.which",return_value="runtime"),patch.object(jobs,"invocation",side_effect=invocation):
            result=jobs.start(self.refs["warm"],"Partial work","hermes","Write then pause")
            deadline=time.monotonic()+5
            while not (Path(result["workspace"])/"partial.txt").exists() and time.monotonic()<deadline:time.sleep(.02)
            jobs.cancel(result["job"])
            for thread in jobs.threads:thread.join(timeout=10)
            state=self.engine.resume(result["attempt"])
            self.assertEqual(state["state"],"interrupted")
            self.assertEqual(self.studio.read(state["revision"],"partial.txt"),b"keep this work")
            job=next(j for j in self.studio.history()["jobs"] if j["id"]==result["job"])
            self.assertEqual(job["state"],"cancelled")

    def test_restarted_controller_fences_an_unconfirmed_old_worker(self):
        branch=self.studio.branch(self.refs["warm"],"Lost runtime")
        with self.engine.db() as db:
            db.execute("INSERT INTO studio_jobs VALUES ('lost',?,'hermes','work','running','',NULL,?,?)",(branch["attempt"],time.time(),time.time()))
        jobs=Jobs(self.studio)
        try:
            self.assertEqual(self.engine.resume(branch["attempt"])["state"],"interrupted")
            with self.assertRaises(WorkgraphError):self.engine.checkpoint(branch["attempt"],session=branch["session"])
            self.assertEqual(self.studio.history()["jobs"][0]["state"],"interrupted")
        finally:jobs.close()

    def test_changing_workers_keeps_one_named_path_and_fences_old_workspace(self):
        path=self.studio.branch(self.refs["warm"],"An idea to continue")
        before=len(self.studio.history()["paths"])
        continued=self.studio.continue_path(path["revision"],"codex","Continue this direction")
        self.assertEqual(len(self.studio.history()["paths"]),before)
        self.assertEqual(continued["name"],"An idea to continue")
        self.assertNotEqual(continued["workspace"],path["workspace"])
        self.assertEqual(self.engine.resume(path["attempt"])["state"],"superseded")
        (Path(continued["workspace"])/"next.txt").write_text("next worker")
        saved=self.engine.checkpoint(continued["attempt"],"Continued by another worker",session=continued["session"],select=False)
        v=next(v for v in self.studio.history()["versions"] if v["id"]==saved["revision"])
        self.assertEqual(v["path"],path["attempt"])
        self.assertEqual(v["parent"],path["revision"])

    def test_earlier_point_requires_an_explicit_new_path(self):
        with self.assertRaises(WorkgraphError) as raised:
            self.studio.continue_path(self.refs["warm"],"hermes","Try again")
        self.assertEqual(raised.exception.code,"EARLIER_VERSION")


if __name__=="__main__":unittest.main()
