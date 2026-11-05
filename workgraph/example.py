"""An interactive, reproducible example backed by real Git and Workgraph operations.

Edits are scripted for the guided tour. No UI state is fabricated. This is also
used as an end-to-end acceptance fixture and video capture source.
"""

import json
import os
from pathlib import Path
import subprocess
import sys
import threading
import uuid

from .engine import Engine, WorkgraphError

API_BASE = 'def profile():\n    return {"name": "Ada Lovelace"}\n'
API_ONE = 'def profile():\n    return {"name": "Ada Lovelace", "role": "member"}\n'
API_TWO = 'def profile():\n    return {"display_name": "Ada Lovelace", "role": "member"}\n'
CLIENT_BASE = 'from api import profile\n\ndef greeting():\n    return profile()["name"]\n'
CLIENT_ONE = 'from api import profile\n\ndef greeting():\n    value = profile()\n    return value["name"] + " · " + value["role"]\n'
CLIENT_TWO = CLIENT_ONE.replace('value["name"]', 'value["display_name"]')
CONTRACT = '''import os, sys
sys.path.insert(0, os.getcwd())
from client import greeting
actual = greeting()
assert actual == "Ada Lovelace · member", f"Unexpected greeting: {actual!r}"
print("PASS — API and client agree. End-to-end greeting: " + actual)
'''

BEATS = [
    {"title": "Start with a real repository", "body": "Two agents will change an API and its client. Every action in this guided example operates on real files and Git objects.", "action": "Start two pieces of work"},
    {"title": "Two agents. One shared understanding.", "body": "The client pins the API's exact provisional revision. Each attempt has its own files, saved decisions, and next steps.", "action": "Interrupt the API session"},
    {"title": "The session stopped. The work survived.", "body": "The latest code, plan, decisions, and open question are saved. A replacement can continue without reconstructing the conversation.", "action": "Hand the work to Codex"},
    {"title": "A dependency changed. Nothing is silently overwritten.", "body": "The replacement changes name to display_name. Workgraph identifies that the client's pinned API revision is outdated and preserves its existing work.", "action": "Reconcile and check the client"},
    {"title": "A clean merge can still be wrong.", "body": "Reconciliation preserves the client's edits, but the frozen integration check catches the old field name. Acceptance is blocked.", "action": "Repair and check a new candidate"},
    {"title": "An exact candidate, with current evidence.", "body": "The repaired client and current API pass the operator's frozen check. The failed candidate and original attempts remain inspectable.", "action": "Accept the checked candidate"},
    {"title": "One clean Git change. The full story stays available.", "body": "Accepted code is an ordinary Git commit. Work, handoffs, alternative history, dependencies, and check results remain queryable.", "action": None},
]


class Example:
    def __init__(self, engine):
        self.engine = engine
        self.path = engine.home / "example.json"
        self.lock = threading.RLock()

    @classmethod
    def create(cls, directory):
        root = Path(directory).resolve()
        if root.exists() and any(root.iterdir()):
            raise WorkgraphError("DIRECTORY_NOT_EMPTY", "The example needs an empty directory so existing work is preserved.")
        root.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
        for name, content in {"api.py": API_BASE, "client.py": CLIENT_BASE, ".gitignore": "__pycache__/\n"}.items():
            (root / name).write_text(content)
        subprocess.run(["git", "-C", str(root), "add", "."], check=True)
        subprocess.run(["git", "-C", str(root), "-c", "user.name=Workgraph Example", "-c", "user.email=example@localhost",
                        "commit", "-qm", "Initial API and client"], check=True)
        engine = Engine(root)
        engine.init()
        check = engine.home / "example-contract.py"
        check.write_text(CONTRACT)
        engine.set_check("integration", [sys.executable, "{check_root}/example-contract.py"], trusted_files=[check])
        result = cls(engine)
        result.save({"id": uuid.uuid4().hex[:12], "phase": 0, "base": engine.target(), "actors": "scripted guided example"})
        return result

    def save(self, value):
        temporary = self.path.with_suffix(".tmp")
        with temporary.open("w") as file:
            json.dump(value, file, indent=2)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(self.path)

    def state(self):
        data = json.loads(self.path.read_text())
        return {**data, "beat": BEATS[data["phase"]], "total": len(BEATS),
                "disclosure": "Guided example. Scripted edits; real repository, handoffs, dependency checks, tests, and acceptance."}

    def advance(self, expected=None):
        with self.lock:
            data = json.loads(self.path.read_text())
            phase = data["phase"]
            if expected is not None and expected != phase:
                return self.state()
            key = lambda suffix: f"example:{data['id']}:{phase}:{suffix}"
            if phase == 0:
                api = self.engine.begin("Migrate the profile API", session="hermes-api", runtime="hermes",
                    constraints=["Migrate the API and client together", "Publish only a passing end-to-end greeting"], request_id=key("api"))
                (Path(api["workspace"]) / "api.py").write_text(API_ONE)
                first = self.engine.checkpoint(api["attempt"], "Added role; response rename remains",
                    plan=["Rename name to display_name", "Reconcile the dependent client"],
                    decisions=["The API and client must be accepted together"],
                    questions=["Which clients still read the name field?"], request_id=key("api-checkpoint"))
                client = self.engine.begin("Update the profile card", session="hermes-client", runtime="hermes",
                    depends_on=[first["revision"]], request_id=key("client"))
                (Path(client["workspace"]) / "client.py").write_text(CLIENT_ONE)
                cr = self.engine.checkpoint(client["attempt"], "Show the member role on the profile card",
                    plan=["Verify against the final API response"], decisions=["Use the API revision supplied by the API worker"], request_id=key("client-checkpoint"))
                data.update(api=api, api_revision=first["revision"], client=client, client_revision=cr["revision"])
            elif phase == 1:
                self.engine.transition(data["api"]["attempt"], "interrupted", request_id=key("interrupt"))
            elif phase == 2:
                new = self.engine.takeover(data["api"]["attempt"], "codex-api", "codex", request_id=key("takeover"))
                (Path(new["workspace"]) / "api.py").write_text(API_TWO)
                revision = self.engine.checkpoint(new["attempt"], "Response now exposes display_name",
                    decisions=["Rename the field and update the dependent client in the same accepted candidate"],
                    questions=[], request_id=key("new-api-checkpoint"))
                data.update(replacement=new, current_api_revision=revision["revision"])
            elif phase == 3:
                new = self.engine.reconcile(data["client"]["attempt"], request_id=key("reconcile"))
                revision = self.engine.checkpoint(new["attempt"], "Client text reconciled with the current API", select=True,
                    request_id=key("client-reconciled"))
                candidate = self.engine.compose([revision["revision"]], request_id=key("candidate"))
                result = self.engine.verify(candidate["candidate"], "integration", request_id=key("check"))
                if result["passed"]:
                    raise AssertionError("The deliberately incompatible example unexpectedly passed")
                data.update(reconciled=new, failed_candidate=candidate["candidate"])
            elif phase == 4:
                new = data["reconciled"]
                (Path(new["workspace"]) / "client.py").write_text(CLIENT_TWO)
                revision = self.engine.checkpoint(new["attempt"], "Client now reads display_name", questions=[],
                    plan=["Review the checked candidate"], request_id=key("repair"))
                candidate = self.engine.compose([revision["revision"]], request_id=key("fixed-candidate"))
                result = self.engine.verify(candidate["candidate"], "integration", request_id=key("fixed-check"))
                if not result["passed"]:
                    raise AssertionError(result["output"])
                data.update(fixed_revision=revision["revision"], ready_candidate=candidate["candidate"])
            elif phase == 5:
                data["accepted"] = self.engine.land(data["ready_candidate"], request_id=key("accept"))
                count = self.engine.git("rev-list", "--count", f"{data['base']}..{self.engine.TARGET}").strip()
                if count != "1":
                    raise AssertionError("The example should export exactly one accepted Git commit")
            else:
                return self.state()
            data["phase"] += 1
            self.save(data)
            return self.state()
