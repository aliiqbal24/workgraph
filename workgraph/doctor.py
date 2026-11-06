import json
import os
from pathlib import Path
import shutil

from .engine import Engine
from .version import __version__


def inspect(repo):
    engine = Engine(repo)
    issues, warnings = [], []
    with engine.db() as db:
        integrity = db.execute("PRAGMA integrity_check").fetchone()[0]
        if integrity != "ok":
            issues.append({"code": "DATABASE_INTEGRITY", "message": integrity})
        for error in db.execute("PRAGMA foreign_key_check"):
            issues.append({"code": "FOREIGN_KEY", "message": str(tuple(error))})
        for revision in db.execute("SELECT id,commit_oid FROM revisions"):
            actual = engine.git("rev-parse", "--verify", f"refs/workgraph/revisions/{revision['id']}", check=False)
            if actual.returncode or actual.stdout.strip() != revision["commit_oid"]:
                issues.append({"code": "REVISION_REF", "object": revision["id"]})
        for attempt in db.execute("SELECT id,workspace,state FROM attempts"):
            if not Path(attempt["workspace"]).is_dir():
                issues.append({"code": "MISSING_WORKSPACE", "object": attempt["id"]})
        pending = [dict(row) for row in db.execute("SELECT id,operation,created FROM requests WHERE state='pending'")]
        if pending:
            warnings.append({"code": "PENDING_OPERATIONS", "count": len(pending), "next_step": "workgraph recover"})
        checks = db.execute("SELECT count(*) FROM checks WHERE required=1").fetchone()[0]
        if not checks:
            warnings.append({"code": "NO_REQUIRED_CHECKS", "message": "Acceptance is unavailable until an operator configures a required check."})
    return {"ok": not issues, "repository": str(engine.repo), "version": __version__, "database": integrity,
            "issues": issues, "warnings": warnings, "pending": pending,
            "sandbox": "unsafe operator opt-in" if os.environ.get("WORKGRAPH_UNSAFE_LOCAL") == "1" else
                       ("bubblewrap" if shutil.which("bwrap") else "unavailable; managed execution blocked"),
            "runtimes": {name: bool(shutil.which(binary)) for name, binary in (("hermes", "hermes"), ("codex", "codex"), ("claude", "claude"))}}
