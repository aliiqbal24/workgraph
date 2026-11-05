"""A real engine demonstration using scripted edits, with no model/API required.

Run: python demo.py
The temporary fixture is removed afterwards; your checkout is never modified.
"""

from pathlib import Path
import subprocess
import sys
import tempfile

from workgraph import Engine, WorkgraphError


POLICY = "REQUIRE_OWNER = False\n\ndef can_read(viewer, owner):\n    return not REQUIRE_OWNER or viewer == owner\n"
CACHE = "ENABLED = False\n\ndef key(viewer, document):\n    return document\n"
APP = '''import policy
import cache

values = {}

def read(viewer, owner, document):
    key = cache.key(viewer, document)
    if cache.ENABLED and key in values:
        return values[key]
    if not policy.can_read(viewer, owner):
        return "DENIED"
    result = "private:" + document
    if cache.ENABLED:
        values[key] = result
    return result
'''
CONTRACT = '''import app, policy
assert app.read("alice", "alice", "payroll") == "private:payroll"
result = app.read("bob", "alice", "payroll")
if policy.REQUIRE_OWNER:
    assert result == "DENIED", "Privacy contract violated: Bob received Alice's cached payroll"
print("Configured privacy contract passed")
'''


def fixture(root):
    subprocess.run(["git", "init", "-q", "-b", "main", str(root)], check=True)
    for name, value in {"policy.py": POLICY, "cache.py": CACHE, "app.py": APP,
                        ".gitignore": "__pycache__/\n"}.items():
        (root / name).write_text(value)
    subprocess.run(["git", "-C", str(root), "add", "."], check=True)
    subprocess.run(["git", "-C", str(root), "-c", "user.name=Demo", "-c",
                    "user.email=demo@localhost", "commit", "-qm", "Initial application"], check=True)
    engine = Engine(root)
    engine.init()
    engine.set_check("privacy", [sys.executable, "-c", CONTRACT])
    return engine


def run(root):
    engine = fixture(root)
    original = engine.git("rev-parse", "main").strip()
    auth = engine.begin("Make documents private to their owners", session="auth-session")
    cache = engine.begin("Cache document reads", session="cache-session")
    (Path(auth["workspace"]) / "policy.py").write_text(POLICY.replace("False", "True"))
    (Path(cache["workspace"]) / "cache.py").write_text(CACHE.replace("False", "True"))
    auth_revision = engine.snapshot(auth["attempt"], "Enforce owner authorization")["revision"]
    cache_revision = engine.snapshot(cache["attempt"], "Enable document caching")["revision"]

    print("Two isolated sessions. Two independent changes.")
    for label, revision in [("Authorization", auth_revision), ("Caching", cache_revision)]:
        candidate = engine.compose([revision])["candidate"]
        result = engine.verify(candidate, "privacy")
        assert result["passed"]
        print(f"  {label}: PASSED its configured check in isolation")

    combined = engine.compose([auth_revision, cache_revision])
    assert combined["state"] == "unverified" and not combined["conflict"]
    result = engine.verify(combined["candidate"], "privacy")
    assert not result["passed"]
    print("\nCompose both: text merge succeeds, privacy check FAILS.")
    print("  Bob receives Alice's cached payroll.")
    try:
        engine.land(combined["candidate"])
        raise AssertionError("Failed composition was accepted")
    except WorkgraphError as error:
        assert error.code == "NOT_READY"
        print("  Landing blocked. Both original changes are preserved.")

    alternative = engine.begin("Try a user-scoped cache", session="repair-session", from_revision=cache_revision)
    (Path(alternative["workspace"]) / "cache.py").write_text(
        CACHE.replace("False", "True").replace("return document", "return (viewer, document)"))
    fixed_revision = engine.snapshot(alternative["attempt"], "Scope cache entries by viewer")["revision"]
    fixed = engine.compose([auth_revision, fixed_revision])
    result = engine.verify(fixed["candidate"], "privacy")
    assert result["passed"]
    engine.land(fixed["candidate"])
    print("\nFork caching attempt, fix cache identity, compose again: PASSED.")
    print("  Accepted as a normal Git commit on workgraph/accepted.")
    print("  Original attempts and failed composition remain inspectable.")
    assert engine.inspect(combined["candidate"])["state"] == "stale"
    assert engine.git("rev-parse", "main").strip() == original
    assert engine.git("status", "--porcelain") == ""
    print("  Your main branch, files, and staging index remain untouched.")


if __name__ == "__main__":
    with tempfile.TemporaryDirectory(prefix="workgraph-demo-") as directory:
        run(Path(directory))
