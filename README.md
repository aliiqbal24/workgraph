# Workgraph: an experiment in version control for agent work

The proposed unit of version control is a **work item**: an intent with multiple
attempts and immutable revisions. A session can end without ending the work.
Several revisions can be composed into a candidate. Validation belongs to that
exact composition, rather than to a branch name or an agent's success claim.

This repository is an executable exploration of those primitives, with a
temporary working name. It is not a finished VCS or a submitted Hermes plugin.

## Run the experiment

Python 3.11+ and Git with `merge-tree --write-tree` are required. There are no
runtime Python dependencies and no model calls.

```bash
python demo.py
python -m unittest discover -s tests -v
```

The demo creates a disposable Git repository. Two scripted sessions add private
document authorization and document caching in isolated workspaces. Each change
passes a configured privacy check separately. They merge without a text conflict,
but fail the same check together: Bob receives Alice's cached payroll. Acceptance
is blocked. A forked caching attempt repairs the interaction; the new composition
passes and becomes one ordinary Git commit. Original attempts and failed
candidates remain available.

The check is explicitly supplied; this is not automatic detection of arbitrary
semantic conflicts. Edits are scripted to demonstrate the storage and acceptance
model, not presented as a live AI-agent run.

## Agent-facing operations

From a Git repository with an initial commit:

```bash
python -m workgraph --repo /path/to/repo init
python -m workgraph --repo /path/to/repo begin 'Make documents private' --session auth
python -m workgraph --repo /path/to/repo snapshot ATTEMPT_ID 'Owner authorization implemented'
python -m workgraph --repo /path/to/repo fork REVISION_ID --session alternative
python -m workgraph --repo /path/to/repo resume ATTEMPT_ID
python -m workgraph --repo /path/to/repo compose REVISION_A REVISION_B
python -m workgraph --repo /path/to/repo verify CANDIDATE_ID privacy
python -m workgraph --repo /path/to/repo inspect CANDIDATE_ID
python -m workgraph --repo /path/to/repo land CANDIDATE_ID
python -m workgraph --repo /path/to/repo status
```

Every command returns JSON. `begin` returns the isolated workspace path an agent
edits. `resume` returns intent, saved context, workspace, revision, and whether
unsaved edits exist. `fork` preserves the work identity while creating a separate
attempt. `compose` selects one revision per work item and preserves text conflicts
as candidate records. It does not alter the source attempts.

An operator supplies required named checks before verification:

```bash
python -m workgraph --repo /path/to/repo set-check test -- python -m unittest
```

Checks run in disposable workspaces and retain their output. Evidence is tied to
the candidate's code tree, accepted base, and check command fingerprint. Changed
checks invalidate old evidence. A moved accepted base invalidates the candidate.
A successful check that modifies nonignored source files is rejected. A candidate
with no configured checks cannot land.

`land` updates only `workgraph/accepted`, using Git's compare-and-swap ref update.
It never rewrites the user's checked-out branch or staging index. The target must
not be checked out. Accepted output contains one conventional Git commit; private
attempt history stays in separate refs.

## Storage and current limits

Git stores source trees and commits under `refs/workgraph/*`. SQLite metadata and
managed workspaces live in the repository's common Git directory under
`workgraph/`, so linked worktrees see the same metadata. Nothing is uploaded.
Snapshots respect Git ignore rules and include nonignored untracked files.

This is a cooperative local tool, not a security boundary. A process with full
filesystem access can bypass its policy. Named checks are operator configuration;
their definitions should not be delegated to the implementation agent. Running
checks executes repository code on the host. Environment/dependency identities
are not yet captured, and passing tests establish only what those tests cover.

Snapshots are explicit and require a quiescent tool boundary. They do not capture
process memory, databases, external API side effects, ignored files, or an entire
agent runtime. Git worktrees and refs can be orphaned if an operation is killed
between Git and SQLite writes; full operation journaling and recovery are future
work. This prototype is for disposable experiments, not valuable repositories.

The next design questions are exact revision dependencies, ownership of attempts,
automatic checkpoints at Hermes tool boundaries, recoverable operations, review
of candidate evidence, and synchronization of metadata between machines.
