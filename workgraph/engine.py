"""A small Git-backed experiment, deliberately independent of any agent runtime.

Git stores immutable trees and commits. SQLite stores work, attempts, candidates,
and check evidence. The user's checkout and staging index are never rewritten.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import time
import uuid


class WorkgraphError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        super().__init__(message)


def identifier(prefix):
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


class Engine:
    TARGET = "refs/heads/workgraph/accepted"

    def __init__(self, repo):
        self.repo = Path(repo).resolve()
        common = self.git("rev-parse", "--path-format=absolute", "--git-common-dir")
        self.home = Path(common.strip()) / "workgraph"
        self.dbpath = self.home / "state.sqlite3"

    def git(self, *args, cwd=None, env=None, input=None, check=True):
        result = subprocess.run(
            ["git", "-C", str(cwd or self.repo), *map(str, args)],
            input=input, text=True, capture_output=True,
            env={**os.environ, **(env or {})},
        )
        if check and result.returncode:
            raise WorkgraphError("GIT_ERROR", result.stderr.strip() or result.stdout.strip())
        return result.stdout if check else result

    @contextlib.contextmanager
    def db(self):
        if not self.dbpath.exists():
            raise WorkgraphError("NOT_INITIALIZED", "Run workgraph init for this repository.")
        connection = sqlite3.connect(self.dbpath, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def init(self):
        base = self.git("rev-parse", "HEAD").strip()
        self.home.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.dbpath) as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS work (
                    id TEXT PRIMARY KEY, intent TEXT NOT NULL, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    id TEXT PRIMARY KEY, work_id TEXT NOT NULL REFERENCES work(id),
                    session TEXT NOT NULL, base TEXT NOT NULL, workspace TEXT NOT NULL,
                    head TEXT, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(id),
                    parent TEXT, commit_oid TEXT NOT NULL, tree_oid TEXT NOT NULL,
                    context TEXT NOT NULL, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS candidates (
                    id TEXT PRIMARY KEY, base TEXT NOT NULL, inputs TEXT NOT NULL,
                    commit_oid TEXT, tree_oid TEXT NOT NULL, conflict TEXT,
                    landed INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS checks (
                    name TEXT PRIMARY KEY, argv TEXT NOT NULL, fingerprint TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS evidence (
                    id TEXT PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES candidates(id),
                    name TEXT NOT NULL, fingerprint TEXT NOT NULL, passed INTEGER NOT NULL,
                    returncode INTEGER, output TEXT NOT NULL, created REAL NOT NULL
                );
            """)
        existing = self.git("rev-parse", "--verify", self.TARGET, check=False)
        if existing.returncode:
            self.git("update-ref", self.TARGET, base, "")
        return {"repository": str(self.repo), "target": self.TARGET, "base": self.target()}

    def target(self):
        return self.git("rev-parse", "--verify", self.TARGET).strip()

    def row(self, db, table, key):
        # Table names come exclusively from internal callers.
        row = db.execute(f"SELECT * FROM {table} WHERE id=?", (key,)).fetchone()
        if row is None:
            raise WorkgraphError("NOT_FOUND", f"Unknown {table} id: {key}")
        return dict(row)

    def commit(self, tree, parents, message):
        args = ["commit-tree", tree]
        for parent in dict.fromkeys(parents):
            args.extend(["-p", parent])
        return self.git(*args, input=message + "\n", env={
            "GIT_AUTHOR_NAME": "Workgraph", "GIT_AUTHOR_EMAIL": "workgraph@localhost",
            "GIT_COMMITTER_NAME": "Workgraph", "GIT_COMMITTER_EMAIL": "workgraph@localhost",
        }).strip()

    def workspace(self, name, commit):
        path = self.home / "workspaces" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        self.git("worktree", "add", "--detach", str(path), commit)
        return path

    def begin(self, intent, session="local", work_id=None, from_revision=None):
        if not intent.strip():
            raise WorkgraphError("INVALID_INTENT", "An intent must describe the work.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            if work_id:
                self.row(db, "work", work_id)
            if from_revision:
                revision = self.row(db, "revisions", from_revision)
                source = self.row(db, "attempts", revision["attempt_id"])
                if work_id and source["work_id"] != work_id:
                    raise WorkgraphError("WRONG_WORK", "A fork must belong to the same work.")
                work_id = source["work_id"]
                base = revision["commit_oid"]
            else:
                base = self.target()
            if not work_id:
                work_id = identifier("work")
                db.execute("INSERT INTO work VALUES (?, ?, ?)", (work_id, intent, time.time()))
            attempt_id = identifier("attempt")
            path = self.workspace(attempt_id, base)
            db.execute("INSERT INTO attempts VALUES (?, ?, ?, ?, ?, NULL, ?)", (
                attempt_id, work_id, session, base, str(path), time.time(),
            ))
        return {"work": work_id, "attempt": attempt_id, "workspace": str(path), "base": base}

    def tree(self, workspace):
        # An alternate index avoids touching the agent's staging index.
        with tempfile.TemporaryDirectory(prefix="workgraph-index-") as directory:
            env = {"GIT_INDEX_FILE": str(Path(directory) / "index")}
            self.git("read-tree", "HEAD", cwd=workspace, env=env)
            self.git("add", "-A", "--", ".", cwd=workspace, env=env)
            return self.git("write-tree", cwd=workspace, env=env).strip()

    def snapshot(self, attempt_id, summary, decisions=None):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            attempt = self.row(db, "attempts", attempt_id)
            tree = self.tree(attempt["workspace"])
            if tree != self.tree(attempt["workspace"]):
                raise WorkgraphError("WORKSPACE_CHANGED", "Pause writes before taking a snapshot.")
            parent = attempt["base"]
            if attempt["head"]:
                parent = self.row(db, "revisions", attempt["head"])["commit_oid"]
            context = {"summary": summary, "decisions": decisions or [], "session": attempt["session"]}
            revision_id = identifier("rev")
            commit = self.commit(tree, [parent], summary)
            self.git("update-ref", f"refs/workgraph/revisions/{revision_id}", commit, "")
            db.execute("INSERT INTO revisions VALUES (?, ?, ?, ?, ?, ?, ?)", (
                revision_id, attempt_id, attempt["head"], commit, tree,
                json.dumps(context), time.time(),
            ))
            db.execute("UPDATE attempts SET head=? WHERE id=?", (revision_id, attempt_id))
        return {"revision": revision_id, "work": attempt["work_id"], "tree": tree, "context": context}

    def compose(self, revision_ids):
        if not revision_ids or len(set(revision_ids)) != len(revision_ids):
            raise WorkgraphError("INVALID_INPUTS", "Select one or more distinct revisions.")
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            revisions = [self.row(db, "revisions", key) for key in revision_ids]
            work_ids = [self.row(db, "attempts", r["attempt_id"])["work_id"] for r in revisions]
            if len(set(work_ids)) != len(work_ids):
                raise WorkgraphError("ALTERNATIVES", "Choose one revision per work; attempts are alternatives.")
            candidate_id = identifier("candidate")
            base = current = self.target()
            tree = self.git("rev-parse", f"{base}^{{tree}}").strip()
            conflict = None
            for revision in revisions:
                merged = self.git("merge-tree", "--write-tree", current, revision["commit_oid"], check=False)
                if merged.returncode not in (0, 1):
                    raise WorkgraphError("MERGE_ERROR", merged.stderr.strip())
                tree = merged.stdout.splitlines()[0]
                if merged.returncode == 1:
                    conflict = merged.stdout.partition("\n")[2]
                    current = None
                    break
                current = self.commit(tree, [current, revision["commit_oid"]], f"Compose {candidate_id}")
            if current:
                # Export one conventional commit. Experimental revision ancestry
                # remains private under refs/workgraph instead of polluting Git log.
                intents = [self.row(db, "work", key)["intent"] for key in work_ids]
                current = self.commit(tree, [base], "Workgraph: " + "; ".join(intents)
                                      + f"\n\nCandidate: {candidate_id}")
                self.git("update-ref", f"refs/workgraph/candidates/{candidate_id}", current, "")
            else:
                # Pin the conflict tree too; conflicts are durable records.
                self.git("update-ref", f"refs/workgraph/conflicts/{candidate_id}", tree, "")
            db.execute("INSERT INTO candidates VALUES (?, ?, ?, ?, ?, ?, 0, ?)", (
                candidate_id, base, json.dumps(revision_ids), current, tree, conflict, time.time(),
            ))
        return self.inspect(candidate_id)

    def set_check(self, name, argv):
        """Operator configuration. Deliberately absent from the agent plugin."""
        if not name or not argv or not all(isinstance(arg, str) for arg in argv):
            raise WorkgraphError("INVALID_CHECK", "Provide a name and nonempty argv list.")
        with self.db() as db:
            db.execute("INSERT OR REPLACE INTO checks VALUES (?, ?, ?)", (
                name, json.dumps(argv), digest(argv),
            ))
        return {"check": name, "fingerprint": digest(argv)}

    def evidence_fingerprint(self, candidate, check):
        return digest({"base": candidate["base"], "tree": candidate["tree_oid"],
                       "check": check["fingerprint"]})

    def verify(self, candidate_id, name, timeout=60):
        with self.db() as db:
            candidate = self.row(db, "candidates", candidate_id)
            check = db.execute("SELECT * FROM checks WHERE name=?", (name,)).fetchone()
            if check is None:
                raise WorkgraphError("UNKNOWN_CHECK", "An operator must configure this named check.")
            check = dict(check)
        if candidate["conflict"]:
            raise WorkgraphError("CONFLICTED", "This composition has unresolved text conflicts.")
        if self.target() != candidate["base"]:
            raise WorkgraphError("STALE_BASE", "The accepted state moved. Compose a new candidate.")
        path = self.workspace(identifier("check"), candidate["commit_oid"])
        code = None
        try:
            result = subprocess.run(json.loads(check["argv"]), cwd=path, text=True,
                                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=timeout)
            code = result.returncode
            output = result.stdout[-16000:]
            unchanged = self.tree(path) == candidate["tree_oid"]
            passed = code == 0 and unchanged
            if not unchanged:
                output += "\nCheck modified source files; evidence rejected."
        except subprocess.TimeoutExpired as error:
            output = f"Check timed out after {timeout}s.\n{error.stdout or b''}"
            passed = False
        except OSError as error:
            output = str(error)
            passed = False
        finally:
            # Only disposable check workspaces are removed, never agent workspaces.
            self.git("worktree", "remove", "--force", str(path))
        evidence_id = identifier("evidence")
        with self.db() as db:
            db.execute("INSERT INTO evidence VALUES (?, ?, ?, ?, ?, ?, ?, ?)", (
                evidence_id, candidate_id, name, self.evidence_fingerprint(candidate, check),
                int(passed), code, output, time.time(),
            ))
        return {"evidence": evidence_id, "passed": passed, "output": output,
                "candidate": self.inspect(candidate_id)}

    def inspect(self, candidate_id):
        with self.db() as db:
            candidate = self.row(db, "candidates", candidate_id)
            checks = [dict(r) for r in db.execute("SELECT * FROM checks ORDER BY name")]
            evidence = [dict(r) for r in db.execute(
                "SELECT * FROM evidence WHERE candidate_id=? ORDER BY created DESC, rowid DESC", (candidate_id,))]
        results = {}
        for check in checks:
            latest = next((e for e in evidence if e["name"] == check["name"]), None)
            if latest is None:
                results[check["name"]] = "untested"
            elif latest["fingerprint"] != self.evidence_fingerprint(candidate, check):
                results[check["name"]] = "stale"
            else:
                results[check["name"]] = "passed" if latest["passed"] else "failed"
        target = self.target()
        if candidate["landed"]:
            state = "landed"
        elif candidate["conflict"]:
            state = "conflicted"
        elif target != candidate["base"]:
            state = "stale"
        elif "failed" in results.values():
            state = "failed"
        elif results and all(value == "passed" for value in results.values()):
            state = "ready"
        else:
            state = "unverified"
        return {"candidate": candidate_id, "state": state, "base": candidate["base"],
                "tree": candidate["tree_oid"], "revisions": json.loads(candidate["inputs"]),
                "checks": results, "conflict": candidate["conflict"]}

    def land(self, candidate_id):
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            candidate = self.row(db, "candidates", candidate_id)
            if candidate["landed"]:
                return {"candidate": candidate_id, "state": "landed", "commit": candidate["commit_oid"]}
            # Reconcile a crash after the ref write but before the DB commit.
            if candidate["commit_oid"] and self.target() == candidate["commit_oid"]:
                db.execute("UPDATE candidates SET landed=1 WHERE id=?", (candidate_id,))
            else:
                state = self.inspect(candidate_id)
                if state["state"] != "ready":
                    raise WorkgraphError("NOT_READY", f"Candidate is {state['state']}; passing current checks are required.")
                worktrees = self.git("worktree", "list", "--porcelain")
                if f"branch {self.TARGET}\n" in worktrees:
                    raise WorkgraphError("CHECKED_OUT", "The accepted branch must not be checked out during landing.")
                result = self.git("update-ref", self.TARGET, candidate["commit_oid"], candidate["base"], check=False)
                if result.returncode:
                    raise WorkgraphError("STALE_BASE", "The accepted state changed before landing; recompose and recheck.")
                db.execute("UPDATE candidates SET landed=1 WHERE id=?", (candidate_id,))
        return {"candidate": candidate_id, "state": "landed", "commit": candidate["commit_oid"], "target": self.TARGET}

    def status(self):
        with self.db() as db:
            work = [dict(r) for r in db.execute("SELECT * FROM work ORDER BY created")]
            attempts = [dict(r) for r in db.execute("SELECT * FROM attempts ORDER BY created")]
            revisions = [dict(r) for r in db.execute("SELECT * FROM revisions ORDER BY created")]
            candidates = [r[0] for r in db.execute("SELECT id FROM candidates ORDER BY created")]
        for revision in revisions:
            revision["context"] = json.loads(revision["context"])
        return {"target": self.target(), "work": work, "attempts": attempts,
                "revisions": revisions, "candidates": [self.inspect(key) for key in candidates]}

    def resume(self, attempt_id):
        """Return a handoff bundle; this does not restore a model's process memory."""
        with self.db() as db:
            attempt = self.row(db, "attempts", attempt_id)
            work = self.row(db, "work", attempt["work_id"])
            revision = self.row(db, "revisions", attempt["head"]) if attempt["head"] else None
        saved_tree = revision["tree_oid"] if revision else self.git(
            "rev-parse", f"{attempt['base']}^{{tree}}").strip()
        return {
            "work": work["id"], "intent": work["intent"], "attempt": attempt_id,
            "workspace": attempt["workspace"], "session": attempt["session"],
            "revision": attempt["head"], "unsaved_changes": self.tree(attempt["workspace"]) != saved_tree,
            "context": json.loads(revision["context"]) if revision else {},
            "accepted_state_moved": self.target() != attempt["base"],
        }
