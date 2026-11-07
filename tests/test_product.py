"""Product-state invariants, including SQLite-only history and branch isolation."""

from pathlib import Path
from contextlib import closing
import json
import sqlite3
import tempfile
import unittest
from unittest.mock import patch

from workgraph.playground import Playground
from workgraph.studio import Studio
from workgraph.product_state import ProductState
from workgraph.errors import WorkgraphError


class ProductTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.engine = Playground.create(Path(self.temp.name) / "project")
        self.studio = Studio(self.engine)
        self.states = ProductState(self.engine)
        self.origin = self.studio.history()["current"]
        self.states.configure(
            {
                "name": "SQLite app",
                "command": ["{python}", "app.py", "--port", "{port}"],
                "data_files": [".workgraph-data/app.db"],
            }
        )
        self.attempt = self.studio.branch(self.origin, "Working application")
        self.root = Path(self.attempt["workspace"])
        (self.root / ".workgraph-data").mkdir()
        self.database = self.root / ".workgraph-data/app.db"

    def connection(self):
        return sqlite3.connect(self.database)

    def test_source_change_during_state_backup_does_not_publish_a_mixed_version(self):
        capture = ProductState.capture
        before = len(self.engine.status()["revisions"])

        def changed(service, *args):
            result = capture(service, *args)
            (self.root / "concurrent.txt").write_text("A write during state capture")
            return result

        with patch.object(ProductState, "capture", changed):
            with self.assertRaises(WorkgraphError) as caught:
                self.engine.checkpoint(self.attempt["attempt"], "A concurrent capture")
        self.assertEqual(caught.exception.code, "WORKSPACE_CHANGED")
        self.assertEqual(len(self.engine.status()["revisions"]), before)

    def test_database_only_changes_create_versions_and_forks_restore_exact_wal_rows(
        self,
    ):
        with closing(self.connection()) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("CREATE TABLE notes(text TEXT)")
            db.execute("INSERT INTO notes VALUES ('first')")
            db.commit()
            first = self.engine.checkpoint(
                self.attempt["attempt"], "A saved app", select=False
            )["revision"]
            db.execute("INSERT INTO notes VALUES ('second')")
            db.commit()
            second = self.engine.checkpoint(self.attempt["attempt"], select=False)[
                "revision"
            ]
        self.assertNotEqual(first, second)
        self.assertEqual(
            self.studio.revision(first)["tree_oid"],
            self.studio.revision(second)["tree_oid"],
        )
        self.assertNotEqual(
            self.states.get(first)["fingerprint"],
            self.states.get(second)["fingerprint"],
        )
        self.assertNotIn(".workgraph-data/app.db", self.studio.files(second))
        for revision, expected in [(first, 1), (second, 2)]:
            branch = self.studio.branch(revision, "Independent " + str(expected))
            with closing(
                sqlite3.connect(Path(branch["workspace"]) / ".workgraph-data/app.db")
            ) as db:
                self.assertEqual(
                    db.execute("SELECT count(*) FROM notes").fetchone()[0], expected
                )
                db.execute("INSERT INTO notes VALUES ('private change')")
                db.commit()
        again = self.studio.branch(first, "Still the original")
        with closing(
            sqlite3.connect(Path(again["workspace"]) / ".workgraph-data/app.db")
        ) as db:
            self.assertEqual(db.execute("SELECT count(*) FROM notes").fetchone()[0], 1)

    def test_unchanged_source_and_state_deduplicate_and_takeover_restores_own_copy(
        self,
    ):
        with closing(self.connection()) as db:
            db.execute("CREATE TABLE notes(text TEXT)")
            db.execute("INSERT INTO notes VALUES ('kept')")
            db.commit()
        first = self.engine.checkpoint(self.attempt["attempt"], "Saved", select=False)[
            "revision"
        ]
        again = self.engine.checkpoint(self.attempt["attempt"], select=False)
        self.assertEqual(first, again["revision"])
        replacement = self.engine.takeover(
            self.attempt["attempt"], "next worker", "codex"
        )
        with closing(
            sqlite3.connect(Path(replacement["workspace"]) / ".workgraph-data/app.db")
        ) as db:
            self.assertEqual(db.execute("SELECT text FROM notes").fetchone()[0], "kept")
        self.assertEqual(
            self.engine.resume(self.attempt["attempt"])["state"], "superseded"
        )

    def test_state_paths_and_recipe_settings_cannot_redirect_into_host_files(self):
        for definition in [
            {
                "name": "bad",
                "command": ["python", "app.py", "{port}"],
                "data_files": ["../outside.db"],
            },
            {
                "name": "bad",
                "command": ["python", "app.py", "{port}"],
                "data_files": ["app.db"],
            },
            {
                "name": "bad",
                "command": ["python", "app.py", "{port}"],
                "environment": {"PYTHONPATH": "/host"},
            },
            {
                "name": "bad",
                "command": ["python", "app.py", "{port}"],
                "screens": [{"name": "outside", "path": "//example.com"}],
            },
        ]:
            with self.assertRaises(WorkgraphError):
                self.states.configure(definition)
        outside = Path(self.temp.name) / "outside.db"
        outside.write_text("not a project database")
        self.database.symlink_to(outside)
        with self.assertRaises(WorkgraphError):
            self.engine.checkpoint(self.attempt["attempt"], "Refused")

    def test_old_code_only_versions_do_not_claim_a_database_snapshot(self):
        self.assertIsNone(self.states.get(self.origin))
        profile = self.states.get(self.attempt["revision"])
        self.assertEqual(profile["manifest"]["files"], {})
        self.assertEqual(profile["manifest"]["missing"], [".workgraph-data/app.db"])


if __name__ == "__main__":
    unittest.main()
