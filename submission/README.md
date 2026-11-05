# Workgraph submission packet

V1 and its demo are prepared locally. No public repository, catalog PR, social
post, or application has been published by this workflow. Proposed repository:
`https://github.com/aliiqbal24/workgraph` (not created yet).

## Entry text

**Workgraph — the work outlives the worker.**

Agents can write code quickly. Their unfinished engineering situation is still
fragile: a session ends, a replacement rebuilds context, or another worker advances
a provisional dependency. A clean Git merge does not establish that the composed
behavior works.

Workgraph gives unfinished work a persistent identity. Isolated attempts save
source with explicit plans, decisions, and open questions. Dependents pin exact
provisional revisions. Handoffs create fresh workspaces and preserve predecessors.
Candidates need current, operator-configured evidence before the operator can
accept an ordinary Git commit.

The native Hermes plugin uses public tools, lifecycle hooks, and request/execution
middleware to route and automatically capture managed foreground operations.
Codex and Claude Code share a stdio MCP tool and local launch/hook bridges. The
product includes a private localhost dashboard, CLI, recovery, Linux sandboxed
checks, and a reproducible guided example. It owns no model credentials and sends
no telemetry.

## What the demo proves

The guided example performs real repository operations with explicitly scripted
edits: an API worker is interrupted, its work is handed off, the dependent client
becomes outdated, a textually clean composition fails an independent frozen
integration check, and the repaired candidate is accepted as one Git commit.
The failed candidate and old attempts remain inspectable. A separate screen shows
the saved result of an actual native Hermes session with automatic tool capture.

Relay is an original animated AI presenter. The narration is synthesized locally;
the screenshots and browser interaction recordings come from the actual product.

## Validation

- 32 distinct core/interface/regression tests passed.
- Isolated Chromium passed the complete tour, normal work creation, mobile-width
  overflow check, and browser-error check.
- Real Python MCP ClientSession passed discovery, work creation, checkpointing,
  request replay, and the operator acceptance boundary.
- Installed Hermes 0.21.0 Plugin Doctor passed registration. An actual Hermes
  oneshot session routed write_file and terminal through the managed attempt,
  captured both operations, saved context, and left the original checkout intact.
- A clean wheel install ran the complete example outside the source checkout.

Current catalog CI is a separate check; the local Hermes installation provides
Doctor rather than the newer `plugins validate` command. Do not represent that
CI check as passed before the upstream PR runs it.

## Reviewer disclosures

The plugin reads/writes the selected Git repository, its common Git directory,
and managed workspaces. It invokes Git and approved foreground shell/check
commands, stores source/context/check output/event metadata/retry receipts locally,
and can serve a token-authenticated localhost UI. Normal agent shell commands can
use the network; check execution has a private network namespace. It does not
fetch/replace its own code, access credential stores, change host approvals, or
patch Hermes core.

Linux, Python 3.11+, Git 2.43+, and working bubblewrap are required for the default
managed execution modes. An explicit unsafe operator opt-in exists and is not used
in the submitted demonstration. Codex/Claude per-tool capture depends on reviewed
host hooks; launch alone provides MCP plus a final checkpoint. Restored state is
captured source and explicit notes, not hidden model state or external effects.

The specific improvement is coherent unfinished work across interruption,
handoff, and dependency changes. This release does not claim universal semantic
conflict detection or superiority over every existing version-control tool.

## Publication sequence

1. Review the finished video and the prepared public files.
2. Publish the proposed repository and the exact release commit/tag; upload the
   source archive, Python wheel, MP4, captions, and poster as release assets.
3. Add the prepared `workgraph.yaml` under `plugin-catalog/` in a PR to
   NousResearch/hermes-agent. Its pin must be the final published commit. Use
   `catalog-pr.md` as the PR body and read the catalog CI findings.
4. Post the attached demo using `social-post.txt`; copy the actual post URL and
   catalog PR URL into the application. Submit through the organizer's form.

Catalog admission instructions:
https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission

Production project and finished media on this machine:
`/home/ali/Videos/workgraph-v1/`. The source scripts, narration takes, duration
timings, original captures, and verification outputs are retained there.
