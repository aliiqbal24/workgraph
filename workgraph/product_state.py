"""Immutable development state alongside Git source. Recipes are operator-owned.

SQLite snapshots use its online backup API. No model credentials or process RAM
are captured. Source checkpoints remain usable if no app profile is configured.
"""

from pathlib import Path, PurePosixPath
from contextlib import closing
import hashlib
import json
import os
import sqlite3
import tempfile
import time

from .errors import WorkgraphError

SCHEMA = """
CREATE TABLE IF NOT EXISTS app_profiles (
 id TEXT PRIMARY KEY, definition TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS app_attempt_profiles (
 attempt_id TEXT PRIMARY KEY REFERENCES attempts(id), profile_id TEXT NOT NULL REFERENCES app_profiles(id)
);
CREATE TABLE IF NOT EXISTS app_states (
 revision_id TEXT PRIMARY KEY REFERENCES revisions(id), profile_id TEXT NOT NULL REFERENCES app_profiles(id),
 fingerprint TEXT NOT NULL, manifest TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS product_artifacts (
 revision_id TEXT PRIMARY KEY REFERENCES revisions(id), fingerprint TEXT NOT NULL,
 state TEXT NOT NULL, manifest TEXT NOT NULL DEFAULT '{}', error TEXT, updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS product_flows (
 id TEXT PRIMARY KEY, baseline TEXT NOT NULL REFERENCES revisions(id), name TEXT NOT NULL,
 definition TEXT NOT NULL, fingerprint TEXT NOT NULL, created REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS product_flow_bindings (
 revision_id TEXT NOT NULL REFERENCES revisions(id), flow_id TEXT NOT NULL REFERENCES product_flows(id),
 PRIMARY KEY(revision_id,flow_id)
);
CREATE TABLE IF NOT EXISTS product_flow_runs (
 id TEXT PRIMARY KEY, revision_id TEXT NOT NULL REFERENCES revisions(id), fingerprint TEXT NOT NULL,
 state TEXT NOT NULL, results TEXT NOT NULL DEFAULT '[]', created REAL NOT NULL, updated REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS product_lineage (
 revision_id TEXT NOT NULL REFERENCES revisions(id), source_revision TEXT NOT NULL REFERENCES revisions(id),
 kind TEXT NOT NULL, description TEXT NOT NULL, PRIMARY KEY(revision_id,source_revision,kind)
);
CREATE TABLE IF NOT EXISTS product_job_intents (
 job_id TEXT PRIMARY KEY, source_revision TEXT NOT NULL REFERENCES revisions(id), kind TEXT NOT NULL, description TEXT NOT NULL
);
"""


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(
            value, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode()
    ).hexdigest()


def project_path(root, value):
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise WorkgraphError(
            "INVALID_PATH", "Choose a relative file inside the project."
        )
    parts = PurePosixPath(value).parts
    if value.startswith("/") or any(p in ("..", ".git") for p in parts):
        raise WorkgraphError(
            "INVALID_PATH",
            "Project state must stay inside its workspace, outside Git metadata.",
        )
    root = Path(root).resolve()
    path = root / value
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise WorkgraphError(
            "UNSAFE_STATE_PATH", "A symbolic link cannot redirect development state."
        )
    return path


class ProductState:
    def __init__(self, engine):
        self.engine = engine
        self.home = engine.home / "product"

    @staticmethod
    def available(db):
        return bool(
            db.execute(
                "SELECT 1 FROM sqlite_master WHERE name='app_profiles'"
            ).fetchone()
        )

    def configure(self, definition):
        if not isinstance(definition, dict):
            raise WorkgraphError("INVALID_PROFILE", "Provide a development app recipe.")
        allowed = {
            "name",
            "command",
            "prepare",
            "health",
            "data_files",
            "screens",
            "environment",
        }
        if set(definition) - allowed:
            raise WorkgraphError(
                "INVALID_PROFILE", "This app recipe contains unsupported fields."
            )
        name = definition.get("name", "")
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            raise WorkgraphError(
                "INVALID_PROFILE", "Name this application in 1–100 characters."
            )
        command = definition.get("command")

        def argv(value):
            return (
                isinstance(value, list)
                and 0 < len(value) <= 50
                and all(isinstance(x, str) and 0 < len(x) < 2000 for x in value)
            )

        if not argv(command) or "{port}" not in " ".join(command):
            raise WorkgraphError(
                "INVALID_PROFILE", "Provide a command argument list including {port}."
            )
        prepare = definition.get("prepare", [])
        if (
            not isinstance(prepare, list)
            or len(prepare) > 5
            or not all(argv(x) for x in prepare)
        ):
            raise WorkgraphError(
                "INVALID_PROFILE", "Use at most five explicit setup commands."
            )
        files = definition.get("data_files", [])
        if not isinstance(files, list) or len(files) > 4:
            raise WorkgraphError(
                "INVALID_PROFILE", "Choose at most four SQLite development databases."
            )
        for file in files:
            path = project_path(self.engine.repo, file)
            if not str(file).startswith(".workgraph-data/"):
                raise WorkgraphError(
                    "INVALID_PROFILE",
                    "Put development databases under the dedicated .workgraph-data/ directory.",
                )
            if path.suffix.lower() not in (".db", ".sqlite", ".sqlite3"):
                raise WorkgraphError(
                    "INVALID_PROFILE",
                    "Development state currently supports SQLite database files.",
                )
        if self.engine.git("ls-files", "--", ".workgraph-data").strip():
            raise WorkgraphError(
                "TRACKED_STATE",
                "Development databases must be separate from tracked source. Move tracked data out of .workgraph-data before connecting this recipe.",
            )
        screens = definition.get("screens", [{"name": "Overview", "path": "/"}])
        if not isinstance(screens, list) or not 1 <= len(screens) <= 8:
            raise WorkgraphError(
                "INVALID_PROFILE", "Choose one to eight representative screens."
            )
        for screen in screens:
            if not isinstance(screen, dict) or set(screen) - {
                "name",
                "path",
                "width",
                "height",
                "ready",
            }:
                raise WorkgraphError(
                    "INVALID_PROFILE", "Each screen needs a name and a local route."
                )
            if "ready" in screen and (
                not isinstance(screen["ready"], str) or len(screen["ready"]) > 500
            ):
                raise WorkgraphError(
                    "INVALID_PROFILE", "A screen readiness selector must be short text."
                )
            route = screen.get("path", "")
            if (
                not isinstance(route, str)
                or not route.startswith("/")
                or route.startswith("//")
                or len(route) > 500
            ):
                raise WorkgraphError(
                    "INVALID_PROFILE", "Screen routes must be local to this app."
                )
            if not isinstance(screen.get("name"), str) or not screen["name"].strip():
                raise WorkgraphError("INVALID_PROFILE", "Name every screen.")
            for key, default in (("width", 1280), ("height", 800)):
                if (
                    type(screen.get(key, default)) is not int
                    or not 320 <= screen.get(key, default) <= 2000
                ):
                    raise WorkgraphError(
                        "INVALID_PROFILE",
                        "Screen dimensions must be between 320 and 2000 pixels.",
                    )
        health = definition.get("health", "/")
        if (
            not isinstance(health, str)
            or not health.startswith("/")
            or health.startswith("//")
        ):
            raise WorkgraphError("INVALID_PROFILE", "Use a local readiness route.")
        environment = definition.get("environment", {})
        if (
            not isinstance(environment, dict)
            or len(environment) > 20
            or not all(
                isinstance(k, str)
                and k.replace("_", "").isalnum()
                and isinstance(v, str)
                and len(v) < 2000
                for k, v in environment.items()
            )
        ):
            raise WorkgraphError(
                "INVALID_PROFILE",
                "Use a small map of explicit non-secret development settings.",
            )
        if any(
            k.startswith(("GIT_", "LD_", "PYTHON"))
            or k in ("HOME", "PATH", "BASH_ENV", "ENV")
            for k in environment
        ):
            raise WorkgraphError(
                "INVALID_PROFILE",
                "Runtime interpreter and host paths cannot be overridden by an app recipe.",
            )
        profile = {
            "name": name.strip(),
            "command": command,
            "prepare": prepare,
            "health": health,
            "data_files": files,
            "screens": screens,
            "environment": environment,
        }
        key = "profile_" + fingerprint(profile)[:24]
        with self.engine.store.lock(), self.engine.db() as db:
            db.execute(
                "INSERT OR IGNORE INTO app_profiles VALUES (?,?,?)",
                (key, json.dumps(profile), time.time()),
            )
            db.execute(
                "INSERT OR REPLACE INTO settings VALUES ('app_profile',?)", (key,)
            )
        return {"id": key, **profile}

    def profile(self, db, attempt=None, revision=None):
        if not self.available(db):
            return None
        row = None
        if revision:
            row = db.execute(
                "SELECT p.* FROM app_profiles p JOIN app_states s ON s.profile_id=p.id WHERE s.revision_id=?",
                (revision,),
            ).fetchone()
        if not row and attempt:
            row = db.execute(
                "SELECT p.* FROM app_profiles p JOIN app_attempt_profiles a ON a.profile_id=p.id WHERE a.attempt_id=?",
                (attempt,),
            ).fetchone()
        if not row and not revision:
            row = db.execute(
                "SELECT p.* FROM app_profiles p JOIN settings s ON s.value=p.id WHERE s.key='app_profile'"
            ).fetchone()
        return {"id": row["id"], **json.loads(row["definition"])} if row else None

    def bind_attempt(self, db, attempt, origin, workspace):
        if not self.available(db):
            return
        profile = self.profile(db, revision=origin) if origin else self.profile(db)
        if profile:
            db.execute(
                "INSERT OR REPLACE INTO app_attempt_profiles VALUES (?,?)",
                (attempt, profile["id"]),
            )
            if origin:
                self.restore(origin, workspace, db=db)

    def blob(self, key):
        if (
            not isinstance(key, str)
            or len(key) != 64
            or any(x not in "0123456789abcdef" for x in key)
        ):
            raise WorkgraphError("INVALID_BLOB", "Unknown saved development state.")
        return self.home / "blobs" / key

    def backup(self, source):
        if source.stat().st_size > 64_000_000:
            raise WorkgraphError(
                "STATE_TOO_LARGE", "SQLite snapshots are limited to 64 MB each."
            )
        directory = self.home / "blobs"
        directory.mkdir(parents=True, exist_ok=True)
        fd, temp = tempfile.mkstemp(prefix="snapshot-", dir=directory)
        os.close(fd)
        temp = Path(temp)
        try:
            deadline = time.monotonic() + 8

            def progress(*args):
                if time.monotonic() > deadline:
                    raise WorkgraphError(
                        "STATE_BUSY",
                        "The development database did not become ready for a consistent snapshot.",
                    )

            with (
                closing(
                    sqlite3.connect(source.as_uri() + "?mode=ro", uri=True, timeout=3)
                ) as src,
                closing(sqlite3.connect(temp)) as dst,
            ):
                src.backup(dst, pages=256, progress=progress, sleep=0.01)
                if dst.execute("PRAGMA quick_check").fetchone()[0] != "ok":
                    raise WorkgraphError(
                        "INVALID_STATE",
                        "The development database did not pass its integrity check.",
                    )
                dst.commit()
            content = temp.read_bytes()
            if len(content) > 64_000_000:
                raise WorkgraphError(
                    "STATE_TOO_LARGE", "SQLite snapshots are limited to 64 MB each."
                )
            key = hashlib.sha256(content).hexdigest()
            destination = self.blob(key)
            if not destination.exists():
                with temp.open("rb") as file:
                    os.fsync(file.fileno())
                temp.replace(destination)
            return key
        finally:
            temp.unlink(missing_ok=True)

    def capture(self, db, attempt, workspace, tree):
        if not self.available(db):
            return None
        profile = self.profile(db, attempt=attempt)
        if not profile:
            return None
        db.execute(
            "INSERT OR IGNORE INTO app_attempt_profiles VALUES (?,?)",
            (attempt, profile["id"]),
        )
        files = {}
        missing = []
        for name in profile["data_files"]:
            source = project_path(workspace, name)
            if source.is_file():
                files[name] = self.backup(source)
            else:
                missing.append(name)
        manifest = {
            "files": files,
            "missing": missing,
            "scope": "SQLite development data; processes and external services are not captured",
        }
        return {
            "profile_id": profile["id"],
            "fingerprint": fingerprint(
                {"tree": tree, "profile": profile["id"], "state": manifest}
            ),
            "manifest": manifest,
        }

    def attach(self, db, revision, state):
        if state:
            db.execute(
                "INSERT INTO app_states VALUES (?,?,?,?,?)",
                (
                    revision,
                    state["profile_id"],
                    state["fingerprint"],
                    json.dumps(state["manifest"]),
                    time.time(),
                ),
            )

    def get(self, revision, db=None):
        if db is None:
            with self.engine.db() as connection:
                return self.get(revision, connection)
        if not self.available(db):
            return None
        row = db.execute(
            "SELECT * FROM app_states WHERE revision_id=?", (revision,)
        ).fetchone()
        return {**dict(row), "manifest": json.loads(row["manifest"])} if row else None

    def restore(self, revision, workspace, db=None):
        state = self.get(revision, db)
        if state:
            for name, key in state["manifest"]["files"].items():
                destination = project_path(workspace, name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                content = self.blob(key).read_bytes()
                if hashlib.sha256(content).hexdigest() != key:
                    raise WorkgraphError(
                        "STATE_CORRUPT",
                        "A saved development snapshot failed its content check.",
                    )
                destination.write_bytes(content)
                destination.chmod(0o600)
        return state

    def copy_databases(self, source, target, profile):
        for name in profile["data_files"]:
            path = project_path(source, name)
            if path.is_file():
                key = self.backup(path)
                destination = project_path(target, name)
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(self.blob(key).read_bytes())
                destination.chmod(0o600)
