"""Repository-local metadata. Git objects remain the source-content store."""

from contextlib import closing, contextmanager
import fcntl
import json
from pathlib import Path
import sqlite3
import time

from .errors import WorkgraphError

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS work (
 id TEXT PRIMARY KEY, intent TEXT NOT NULL, constraints TEXT NOT NULL,
 selected_revision TEXT, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS attempts (
 id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES work(id),
 session TEXT NOT NULL, runtime TEXT NOT NULL, state TEXT NOT NULL,
 base TEXT NOT NULL, accepted_base TEXT NOT NULL, workspace TEXT NOT NULL, head TEXT,
 context TEXT NOT NULL, generation INTEGER NOT NULL DEFAULT 0,
 origin_revision TEXT, created REAL NOT NULL, updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS dependencies (
 attempt_id TEXT NOT NULL REFERENCES attempts(id),
 work_id TEXT NOT NULL REFERENCES work(id), revision_id TEXT NOT NULL,
 PRIMARY KEY (attempt_id, work_id)
);
CREATE TABLE IF NOT EXISTS revisions (
 id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(id),
 work_id TEXT NOT NULL REFERENCES work(id), parent TEXT,
 commit_oid TEXT NOT NULL, tree_oid TEXT NOT NULL, context TEXT NOT NULL,
 dependencies TEXT NOT NULL, environment TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates (
 id TEXT PRIMARY KEY, base TEXT NOT NULL, inputs TEXT NOT NULL,
 manifest TEXT NOT NULL, commit_oid TEXT, tree_oid TEXT NOT NULL,
 conflict TEXT, landed INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS checks (
 name TEXT PRIMARY KEY, argv TEXT NOT NULL, fingerprint TEXT NOT NULL,
 sources TEXT NOT NULL, environment TEXT NOT NULL, required INTEGER NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
 id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES candidates(id),
 name TEXT NOT NULL, fingerprint TEXT NOT NULL, passed INTEGER NOT NULL,
 returncode INTEGER, output TEXT NOT NULL, environment TEXT NOT NULL,
 started REAL NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS events (
 seq INTEGER PRIMARY KEY AUTOINCREMENT, type TEXT NOT NULL,
 object_id TEXT, session TEXT, payload TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS requests (
 id TEXT PRIMARY KEY, operation TEXT NOT NULL, fingerprint TEXT NOT NULL,
 state TEXT NOT NULL, response TEXT, created REAL NOT NULL, updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS landings (
 candidate_id TEXT PRIMARY KEY REFERENCES candidates(id),
 base TEXT NOT NULL, commit_oid TEXT NOT NULL, state TEXT NOT NULL,
 request_id TEXT, evidence TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS tool_receipts (
 id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(id),
 fingerprint TEXT NOT NULL, state TEXT NOT NULL, checkpoint TEXT,
 created REAL NOT NULL, updated REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS revisions_work ON revisions(work_id, created);
CREATE INDEX IF NOT EXISTS evidence_candidate ON evidence(candidate_id, created);
PRAGMA user_version=1;
"""


class Store:
    def __init__(self, home):
        self.home = Path(home)
        self.path = self.home / "state.sqlite3"

    def initialize(self):
        self.home.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            with closing(sqlite3.connect(self.path)) as db:
                version = db.execute("PRAGMA user_version").fetchone()[0]
                old = db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='attempts'").fetchone()
                if version == 0 and old:
                    raise WorkgraphError("PROTOTYPE_STORE", "This is a pre-V1 experimental store. Preserve it and use V1 in a fresh repository.")
                if version not in (0, 1):
                    raise WorkgraphError("UNSUPPORTED_SCHEMA", f"This store uses schema {version}; this release supports 1.")
        with closing(sqlite3.connect(self.path)) as db:
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.executescript(SCHEMA)

    @contextmanager
    def connect(self):
        if not self.path.exists():
            raise WorkgraphError("NOT_INITIALIZED", "Run workgraph init for this repository.")
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA synchronous=FULL")
        if db.execute("PRAGMA user_version").fetchone()[0] != 1:
            db.close()
            raise WorkgraphError("UNSUPPORTED_SCHEMA", "This repository needs a compatible Workgraph release.")
        try:
            with db:
                yield db
        finally:
            db.close()

    @contextmanager
    def lock(self):
        if not self.path.exists():
            raise WorkgraphError("NOT_INITIALIZED", "Run workgraph init for this repository.")
        with (self.home / "operation.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    @staticmethod
    def event(db, kind, object_id=None, session=None, payload=None):
        db.execute("INSERT INTO events(type,object_id,session,payload,created) VALUES (?,?,?,?,?)",
                   (kind, object_id, session, json.dumps(payload or {}), time.time()))

    def finish(self, db, request_id, result, kind, object_id=None, session=None):
        self.event(db, kind, object_id, session, result)
        db.execute("UPDATE requests SET state='done', response=?, updated=? WHERE id=?",
                   (json.dumps(result), time.time(), request_id))
