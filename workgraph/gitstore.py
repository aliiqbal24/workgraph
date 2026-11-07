"""Narrow Git plumbing; never resets the user's working copy or staging index."""

import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile

from .errors import WorkgraphError


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


class GitStore:
    def __init__(self, repo):
        self.repo = Path(repo).resolve()
        root = self.run("rev-parse", "--show-toplevel").strip()
        self.repo = Path(root)
        self.common = Path(self.run("rev-parse", "--path-format=absolute", "--git-common-dir").strip())
        self.home = self.common / "workgraph"

    def run(self, *args, cwd=None, env=None, input=None, check=True, binary=False):
        # Ambient Git overrides can redirect writes despite an explicit -C.
        clean = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        clean.update(env or {})
        result = subprocess.run(["git", "-c", "core.fsync=committed", "-c", "core.hooksPath=/dev/null",
                                 "-C", str(cwd or self.repo), *map(str, args)],
                                text=not binary, capture_output=True, input=input, env=clean)
        if check and result.returncode:
            message = result.stderr.strip() or result.stdout.strip()
            raise WorkgraphError("GIT_ERROR", message.decode(errors="replace") if binary else message)
        return result.stdout if check else result

    def commit(self, tree, parents, message):
        args = ["commit-tree", tree]
        for parent in dict.fromkeys(parents):
            args += ["-p", parent]
        return self.run(*args, input=message + "\n", env={
            "GIT_AUTHOR_NAME": "Workgraph", "GIT_AUTHOR_EMAIL": "workgraph@localhost",
            "GIT_COMMITTER_NAME": "Workgraph", "GIT_COMMITTER_EMAIL": "workgraph@localhost",
        }).strip()

    def pin(self, namespace, key, oid):
        ref = f"refs/workgraph/{namespace}/{key}"
        current = self.run("rev-parse", "--verify", ref, check=False)
        if not current.returncode:
            if current.stdout.strip() != oid:
                raise WorkgraphError("IMMUTABLE_REF", f"Refusing to overwrite immutable object {key}.")
            return
        self.run("update-ref", ref, oid, "")

    def workspace(self, key, commit):
        path = self.home / "workspaces" / key
        path.parent.mkdir(parents=True, exist_ok=True)
        self.run("worktree", "add", "--detach", str(path), commit)
        return path

    def tree(self, workspace, exclude_data=False):
        workspace = Path(workspace).resolve()
        managed = (self.home / "workspaces").resolve()
        if not workspace.is_relative_to(managed):
            raise WorkgraphError("UNMANAGED_WORKSPACE", "Only managed workspaces can be snapshotted.")
        actual_root = Path(self.run("rev-parse", "--show-toplevel", cwd=workspace).strip()).resolve()
        actual_common = Path(self.run("rev-parse", "--path-format=absolute", "--git-common-dir", cwd=workspace).strip()).resolve()
        if actual_root != workspace or actual_common != self.common.resolve():
            raise WorkgraphError("WORKSPACE_IDENTITY_CHANGED", "The managed workspace's Git identity changed; it was not snapshotted.")
        with tempfile.TemporaryDirectory(prefix="workgraph-index-") as directory:
            env = {"GIT_INDEX_FILE": str(Path(directory) / "index")}
            self.run("read-tree", "HEAD", cwd=workspace, env=env)
            if exclude_data:
                # Enumerate first: git add's exclude pathspec can report ignored
                # database directories as an error on recent Git versions.
                names=self.run("ls-files","-z","--cached","--others","--exclude-standard",cwd=workspace,env=env)
                names="\0".join(name for name in names.split("\0") if name and not name.startswith(".workgraph-data/"))
                if names:self.run("add","-A","--pathspec-from-file=-","--pathspec-file-nul",cwd=workspace,env={**env,"GIT_LITERAL_PATHSPECS":"1"},input=names+"\0")
            else:self.run("add", "-A", "--", ".", cwd=workspace, env=env)
            return self.run("write-tree", cwd=workspace, env=env).strip()

    def merge(self, left, right, base=None):
        args = ["merge-tree", "--write-tree"]
        if base:
            args += [f"--merge-base={base}"]
        result = self.run(*args, left, right, check=False)
        if result.returncode not in (0, 1):
            raise WorkgraphError("MERGE_ERROR", result.stderr.strip())
        lines = result.stdout.splitlines()
        if not lines or len(lines[0]) not in (40, 64):
            raise WorkgraphError("MERGE_ERROR", "Git returned no valid merge tree.")
        return lines[0], result.stdout.partition("\n")[2] if result.returncode else None

    def environment(self, workspace=None):
        result = {"python": sys.version.split()[0], "platform": platform.platform(),
                  "git": self.run("--version").strip(), "scope": "local runtime and captured lockfiles"}
        if workspace:
            locks = {}
            for name in ("uv.lock", "poetry.lock", "requirements.txt", "package-lock.json", "pnpm-lock.yaml", "Cargo.lock"):
                path = Path(workspace) / name
                if path.is_file() and not path.is_symlink():
                    locks[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            result["lockfiles"] = locks
        return result

    def runner_environment(self, argv):
        """Identify the check runner, independent of the controller's Python."""
        runner = argv[0]
        resolved = None if "{workspace}" in runner or runner.startswith("./") else shutil.which(runner)
        identity = {"command": runner, "path": resolved}
        if resolved and Path(resolved).is_file():
            identity["sha256"] = hashlib.sha256(Path(resolved).read_bytes()).hexdigest()
        return {"platform": platform.platform(), "runner": identity,
                "environment": {key: os.environ.get(key) for key in ("PATH", "LANG", "LC_ALL")},
                "scope": "runner binary, local platform, sanitized environment; candidate lockfiles are content-addressed"}
