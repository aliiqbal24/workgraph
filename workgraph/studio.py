"""Human-facing saved versions and paths, backed by the existing immutable core."""
from pathlib import Path, PurePosixPath
from html.parser import HTMLParser
import io
import json
import os
import shutil
import uuid
import zipfile

from .errors import WorkgraphError

SCHEMA = '''
CREATE TABLE IF NOT EXISTS studio_paths (
 attempt_id TEXT PRIMARY KEY REFERENCES attempts(id), name TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS studio_path_members (
 attempt_id TEXT PRIMARY KEY REFERENCES attempts(id), path_id TEXT NOT NULL REFERENCES attempts(id)
);
CREATE TABLE IF NOT EXISTS studio_notes (
 revision_id TEXT PRIMARY KEY REFERENCES revisions(id), label TEXT, starred INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS studio_choices (
 key TEXT PRIMARY KEY, value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS studio_sources (
 revision_id TEXT PRIMARY KEY REFERENCES revisions(id), source_revision TEXT NOT NULL REFERENCES revisions(id), paths TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS studio_jobs (
 id TEXT PRIMARY KEY, attempt_id TEXT NOT NULL REFERENCES attempts(id), runtime TEXT NOT NULL,
 prompt TEXT NOT NULL, state TEXT NOT NULL, output TEXT NOT NULL DEFAULT '',
 error TEXT, created REAL NOT NULL, updated REAL NOT NULL
);
'''


class _EntryProbe(HTMLParser):
    def __init__(self,source):
        super().__init__()
        self.requires_build="%PUBLIC_URL%" in source
        self.feed(source)
        self.close()

    def handle_starttag(self,tag,attrs):
        if tag!="script":return
        src=dict(attrs).get("src") or ""
        path=src.split("?",1)[0].split("#",1)[0]
        if PurePosixPath(path).suffix.lower() in (".ts",".tsx",".jsx",".vue",".svelte") or path=="/@vite/client":
            self.requires_build=True


class Studio:
    def __init__(self, engine):
        self.engine = engine
        self._files = {}
        self._preview_entries = {}
        self._preview_notes = {}
        with engine.store.lock(), engine.db() as db:
            db.executescript(SCHEMA)

    def revision(self, key):
        with self.engine.db() as db:
            return self.engine._revision(db, key)

    @staticmethod
    def name(value):
        if not isinstance(value, str) or not value.strip() or len(value) > 120:
            raise WorkgraphError("INVALID_NAME", "Give this version or path a name of 1–120 characters.")
        return value.strip()

    @staticmethod
    def path(value):
        if not isinstance(value, str) or not value or len(value) > 1000 or "\x00" in value or "\\" in value:
            raise WorkgraphError("INVALID_PATH", "Choose a file in the saved project.")
        parts = PurePosixPath(value).parts
        if value.startswith("/") or any(x in ("..", ".git") for x in parts):
            raise WorkgraphError("INVALID_PATH", "Choose a file inside the saved project, outside Git metadata.")
        return str(PurePosixPath(value))

    def files(self, key):
        revision = self.revision(key)
        if key not in self._files:
            result = {}
            for item in self.engine.git("ls-tree", "-rz", "--long", revision["tree_oid"]).split("\0"):
                if not item:
                    continue
                meta, path = item.split("\t", 1)
                mode, kind, oid, size = meta.split()
                if mode in ("100644", "100755") and kind == "blob":
                    result[path] = {"oid": oid, "size": int(size), "executable": mode == "100755"}
            self._files[key] = result
        return self._files[key]

    def read(self, key, path, limit=4_000_000):
        path = self.path(path)
        entry = self.files(key).get(path)
        if not entry:
            raise WorkgraphError("FILE_NOT_FOUND", "This regular file is not in the saved version.")
        if entry["size"] > limit:
            raise WorkgraphError("FILE_TOO_LARGE", "This file is too large for a saved preview or transfer.")
        return self.engine.git("cat-file", "blob", entry["oid"], binary=True)

    def preview_entry(self, key):
        if key not in self._preview_entries:
            files=self.files(key);entry=None;note="This project has no saved static web entry to preview."
            # Prefer a saved production build over a framework's source index.
            for candidate in ("dist/index.html","index.html","public/index.html","web/index.html"):
                if candidate not in files:continue
                if files[candidate]["size"]>4_000_000:
                    note="This saved page exceeds the 4 MB preview limit.";continue
                source=self.read(key,candidate).decode("utf-8",errors="replace")
                if _EntryProbe(source).requires_build:
                    note="This app needs a saved static build to preview. Its source, history, and agent tools are ready.";continue
                entry=candidate;note="";break
            self._preview_entries[key]=entry;self._preview_notes[key]=note
        return self._preview_entries[key]

    def history(self):
        state = self.engine.status()
        with self.engine.db() as db:
            names = {r["attempt_id"]: r["name"] for r in db.execute("SELECT * FROM studio_paths")}
            notes = {r["revision_id"]: dict(r) for r in db.execute("SELECT * FROM studio_notes")}
            current = db.execute("SELECT value FROM studio_choices WHERE key='current'").fetchone()
            sources = {r["revision_id"]: {"revision": r["source_revision"], "paths": json.loads(r["paths"])} for r in db.execute("SELECT * FROM studio_sources")}
            jobs = [dict(r) for r in db.execute("SELECT * FROM studio_jobs ORDER BY created DESC LIMIT 30")]
            members = {r["attempt_id"]:r["path_id"] for r in db.execute("SELECT * FROM studio_path_members")}
        work = {w["id"]: w for w in state["work"]}
        attempts = {a["id"]: a for a in state["attempts"]}
        versions = []
        for revision in state["revisions"]:
            note = notes.get(revision["id"], {})
            versions.append({"id": revision["id"], "parent": revision["parent"], "path": members.get(revision["attempt_id"],revision["attempt_id"]),"attempt":revision["attempt_id"],
                "work": revision["work_id"], "title": note.get("label") or revision["context"].get("summary") or "Saved version",
                "starred": bool(note.get("starred")), "created": revision["created"], "context": revision["context"],
                "runtime": attempts[revision["attempt_id"]]["runtime"], "preview_entry": self.preview_entry(revision["id"]),"preview_note":self._preview_notes[revision["id"]],
                "source": sources.get(revision["id"]), "file_count": len(self.files(revision["id"]))})
        current_id = current[0] if current else next((w["selected_revision"] for w in state["work"] if w["selected_revision"]), None)
        # A person's chosen point is immutable. Agent results need a new choice,
        # even when they continue the same path. Core integration selection is
        # separate from the human's current direction.
        paths={}
        for a in state["attempts"]:
            pid=members.get(a["id"],a["id"])
            paths[pid]={"id":pid,"attempt":a["id"],"name":names.get(pid,work[a["work_id"]]["intent"]),
                "head":a["head"],"origin":attempts[pid]["origin_revision"],"runtime":a["runtime"],
                "state":a["state"],"workspace":a["workspace"],"created":attempts[pid]["created"]}
        by_revision={r["id"]:r for r in state["revisions"]}
        for job in jobs:
            job["path"]=members.get(job["attempt_id"],job["attempt_id"])
            attempt=attempts[job["attempt_id"]]
            origin,head=by_revision.get(attempt["origin_revision"]),by_revision.get(attempt["head"])
            job["result_revision"]=attempt["head"]
            job["changed_source"]=bool(origin and head and origin["tree_oid"]!=head["tree_oid"])
        return {"repository": state["repository"], "current": current_id, "versions": versions,
            "paths": list(paths.values()),
            "jobs": jobs, "checks": state["checks"], "example": (self.engine.home / "playground.json").exists(),
            "preview_scope": "Saved static web files. Server apps and external services are not started."}

    def note(self, revision, label=None, starred=None, request_id=None):
        self.revision(revision)
        if label is not None:
            label = self.name(label)
        if starred is not None and not isinstance(starred, bool):
            raise WorkgraphError("INVALID_ARGUMENTS", "Starred must be true or false.")
        def action(key):
            with self.engine.db() as db:
                db.execute("INSERT OR IGNORE INTO studio_notes(revision_id) VALUES (?)", (revision,))
                if label is not None:
                    db.execute("UPDATE studio_notes SET label=? WHERE revision_id=?", (label, revision))
                if starred is not None:
                    db.execute("UPDATE studio_notes SET starred=? WHERE revision_id=?", (int(starred), revision))
                return self.engine._finish(db, key, {"revision": revision, "label": label, "starred": starred}, "version.named", revision)
        return self.engine._request("studio.note", {"revision": revision, "label": label, "starred": starred}, action, request_id)

    def archive(self, revision):
        """Portable saved source, with no checkout mutation or Git internals."""
        files=self.files(revision)
        if len(files)>10000 or sum(f["size"] for f in files.values())>100_000_000:
            raise WorkgraphError("ARCHIVE_TOO_LARGE","This saved project exceeds the 100 MB / 10,000 file download limit. Use its managed workspace or ordinary Git export.")
        output=io.BytesIO()
        with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED,compresslevel=6) as archive:
            for name,entry in sorted(files.items()):
                name=self.path(name)
                item=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0))
                item.create_system=3
                item.external_attr=(0o100755 if entry["executable"] else 0o100644)<<16
                item.compress_type=zipfile.ZIP_DEFLATED
                archive.writestr(item,self.read(revision,name,limit=100_000_000))
        return output.getvalue()

    def choose(self, revision, request_id=None):
        self.revision(revision)
        def action(key):
            self.engine.select(revision, key + ":select")
            with self.engine.db() as db:
                db.execute("INSERT OR REPLACE INTO studio_choices VALUES ('current',?)", (revision,))
                return self.engine._finish(db, key, {"revision": revision, "note": "Current direction selected. No files were overwritten or published."}, "version.chosen", revision)
        return self.engine._request("studio.choose", {"revision": revision}, action, request_id, exclusive=False)

    def branch(self, revision, name, runtime="local", prompt=None, session=None, request_id=None):
        name = self.name(name)
        self.revision(revision)
        if runtime not in ("local", "hermes", "codex", "claude", "mcp"):
            raise WorkgraphError("INVALID_RUNTIME", "Choose Hermes, Codex, Claude Code, or a local path.")
        if prompt is not None and (not isinstance(prompt, str) or len(prompt) > 12000):
            raise WorkgraphError("INVALID_PROMPT", "Describe the next step in at most 12,000 characters.")
        payload = {"revision": revision, "name": name, "runtime": runtime, "prompt": prompt, "session": session}
        def action(key):
            owner = session or "studio_" + uuid.uuid4().hex[:16]
            result = self.engine.begin(name, from_revision=revision, session=owner, runtime=runtime, request_id=key+":begin")
            with self.engine.db() as db:
                db.execute("INSERT OR REPLACE INTO studio_paths VALUES (?,?)", (result["attempt"], name))
            context = self.engine.resume(result["attempt"])["context"]
            saved = self.engine.checkpoint(result["attempt"], f"Start {name}",
                plan=([prompt] + context.get("plan", [])) if prompt else context.get("plan", []),
                session=owner, select=False, request_id=key+":save")
            result.update(revision=saved["revision"], name=name, from_revision=revision)
            with self.engine.db() as db:
                return self.engine._finish(db, key, result, "path.created", result["attempt"], owner)
        return self.engine._request("studio.branch", payload, action, request_id, exclusive=False)

    def continue_path(self,revision,runtime,prompt,request_id=None):
        """Change workers at a path's latest point without creating another user path."""
        history=self.history()
        version=next((v for v in history["versions"] if v["id"]==revision),None)
        if not version:raise WorkgraphError("NOT_FOUND","Choose a saved version.")
        path=next(p for p in history["paths"] if p["id"]==version["path"])
        if path["head"]!=revision:
            raise WorkgraphError("EARLIER_VERSION","Start a new direction when continuing an earlier point; later work stays on its existing path.")
        if any(j["path"]==path["id"] and j["state"] in ("queued","running") for j in history["jobs"]):
            raise WorkgraphError("PATH_BUSY","An agent is already working on this path. Stop it or create a new direction.")
        def action(key):
            with self.engine.db() as db:
                current=self.engine.row(db,"attempts",path["attempt"])
                if current["head"]!=revision or current["state"]=="superseded":
                    raise WorkgraphError("PATH_CHANGED","This path advanced while you were choosing. Inspect its latest saved version.")
            result=self.engine.takeover(path["attempt"],"studio_"+uuid.uuid4().hex[:16],runtime,key+":transfer")
            with self.engine.db() as db:
                db.execute("INSERT INTO studio_path_members VALUES (?,?)",(result["attempt"],path["id"]))
                result.update(name=path["name"],revision=revision,from_revision=revision)
                return self.engine._finish(db,key,result,"path.continued",result["attempt"],result["session"])
        return self.engine._request("studio.continue",{"revision":revision,"runtime":runtime,"prompt":prompt},action,request_id,exclusive=False)

    def compare(self, left, right):
        a, b = self.revision(left), self.revision(right)
        parts = self.engine.git("diff", "--no-renames", "--name-status", "-z", a["tree_oid"], b["tree_oid"]).split("\0")
        files = []
        for i in range(0, len(parts)-1, 2):
            status, path = parts[i:i+2]
            files.append({"path": path, "status": status, "title": PurePosixPath(path).stem.replace("-", " ").replace("_", " ").capitalize(),
                          "in_source": path in self.files(right), "transferable": path in self.files(right) or (status == "D" and path in self.files(left))})
        patch = self.engine.git("diff", "--no-ext-diff", "--no-color", a["tree_oid"], b["tree_oid"])
        return {"left": left, "right": right, "files": files, "patch": patch[:100000], "truncated": len(patch)>100000,
                "meaning": "Changes that would turn the left saved source into the right saved source."}

    def combine(self, target, source, paths, name, request_id=None, session=None, runtime="local"):
        name = self.name(name)
        a, b = self.revision(target), self.revision(source)
        if a["work_id"] != b["work_id"]:
            raise WorkgraphError("DIFFERENT_PROJECT_WORK", "Combine versions from the same piece of work.")
        if not isinstance(paths, list) or not paths or len(paths)>100 or not all(isinstance(x,str) for x in paths):
            raise WorkgraphError("CHOOSE_FILES", "Choose between 1 and 100 changed files.")
        paths = list(dict.fromkeys(self.path(x) for x in paths))
        changed = {x["path"]: x for x in self.compare(target, source)["files"]}
        if any(p not in changed or not changed[p]["transferable"] for p in paths):
            raise WorkgraphError("INVALID_TRANSFER", "Only changed regular files or explicit deletions can be brought into another version.")
        contents = {p: self.read(source,p) if p in self.files(source) else None for p in paths}
        if sum(len(x) for x in contents.values() if x is not None)>20_000_000:
            raise WorkgraphError("TRANSFER_TOO_LARGE", "Choose fewer files to combine at once.")
        entries={}
        for item in self.engine.git("ls-tree","-rz",a["tree_oid"]).split("\0"):
            if item:
                meta,path=item.split("\t",1);entries[path]=meta.split()[0]
        deleted={p for p,c in contents.items() if c is None}
        # A file becoming a directory (or vice versa) needs its obstructing files
        # explicitly selected for deletion. Detect this before creating any path.
        for path,content in contents.items():
            if content is None:continue
            blockers=[str(parent) for parent in PurePosixPath(path).parents if str(parent) in entries and str(parent) not in deleted]
            blockers += [p for p in entries if p.startswith(path+"/") and p not in deleted]
            if blockers:
                raise WorkgraphError("INCOMPATIBLE_FILES","Include the matching deletions before bringing these files together, or ask an agent for a finer edit: "+", ".join(blockers[:5]))
        def action(key):
            result = self.branch(target, name, session=session, runtime=runtime, request_id=key+":path")
            root = Path(result["workspace"]).resolve()
            # Delete obstructions first; checkbox click order cannot change the result.
            for path, content in sorted(contents.items(),key=lambda item:(item[1] is not None,-len(PurePosixPath(item[0]).parts))):
                destination = root / path
                if not destination.resolve().is_relative_to(root) or destination.is_symlink():
                    raise WorkgraphError("UNSAFE_FILE", "A symbolic link cannot redirect a file transfer.")
                if content is None:
                    destination.unlink(missing_ok=True)
                else:
                    if destination.is_dir():
                        for directory in sorted((p for p in destination.rglob("*") if p.is_dir()),key=lambda p:len(p.parts),reverse=True):directory.rmdir()
                        destination.rmdir()
                    destination.parent.mkdir(parents=True,exist_ok=True)
                    destination.write_bytes(content)
                    destination.chmod(0o755 if self.files(source)[path]["executable"] else 0o644)
            old = self.engine.resume(result["attempt"])["context"]
            saved = self.engine.checkpoint(result["attempt"], name,
                decisions=old.get("decisions",[])+[f"Brought {', '.join(paths)} from saved version {source}; other files remain from {target}."],
                session=result["session"], select=False, request_id=key+":save")
            result.update(revision=saved["revision"], source=source, paths=paths)
            with self.engine.db() as db:
                db.execute("INSERT OR REPLACE INTO studio_sources VALUES (?,?,?)", (saved["revision"],source,json.dumps(paths)))
                return self.engine._finish(db,key,result,"version.combined",saved["revision"],result["session"])
        return self.engine._request("studio.combine", {"target":target,"source":source,"paths":paths,"name":name,"session":session,"runtime":runtime},action,request_id,exclusive=False)

    def start(self, name="Starting point", request_id=None):
        name = self.name(name)
        def action(key):
            result = self.engine.begin(name, session="studio_local", request_id=key+":begin")
            root = Path(result["workspace"])
            # Capture the chosen repository's present working files without touching its index.
            source_paths = set(filter(None,self.engine.git("ls-files","-z","--cached","--others","--exclude-standard").split("\0")))
            saved_paths = set(filter(None,self.engine.git("ls-files","-z",cwd=root).split("\0")))
            for path in source_paths | saved_paths:
                self.path(path)
                origin, dest = self.engine.repo/path, root/path
                if not dest.parent.resolve().is_relative_to(root.resolve()):
                    raise WorkgraphError("UNSAFE_FILE","A symbolic link cannot redirect a starting-point capture.")
                if dest.is_symlink() or dest.is_file():dest.unlink()
                if origin.is_symlink():
                    dest.parent.mkdir(parents=True,exist_ok=True);dest.symlink_to(os.readlink(origin))
                elif origin.is_file():
                    dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(origin,dest)
            saved=self.engine.checkpoint(result["attempt"],name,session=result["session"],request_id=key+":save")
            with self.engine.db() as db:db.execute("INSERT OR REPLACE INTO studio_paths VALUES (?,?)",(result["attempt"],"Original"))
            self.choose(saved["revision"],key+":choose")
            result["revision"]=saved["revision"]
            with self.engine.db() as db:return self.engine._finish(db,key,result,"studio.started",saved["revision"])
        return self.engine._request("studio.start",{"name":name},action,request_id,exclusive=False)
