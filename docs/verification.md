# V1 verification

## Version 1.1 visual exploration

The current suite contains 56 distinct tests, including safe older-version
selection, exact-parent branching, selected-file composition/deletion, preservation
of unrelated files, immutable source/context, path continuation across workers,
tool retry identities, runtime exit-code propagation, real subprocess capture,
cancellation, controller exclusivity, restart fencing, and an absolute MCP launch
with PYTHONPATH removed. Additional quality checks cover a chosen favorite staying
fixed while that same path advances, exact binary/executable ZIP export, structural
file/directory transfers, setup failure before path takeover, and queued cancellation.

`tests/studio_browser.py` exercises finding an earlier version, making it current,
reload persistence, creating a path from an exact point, side-by-side saved pages,
desktop/phone sizing, combining only Navigation while keeping the original Hero,
expanded previews, and preparing an agent continuation. It checks sandbox isolation,
mobile overflow, page errors, and console errors. The earlier engineering browser
flow remains tested separately at `/engineering`.
It also opens a new project with unstaged and untracked files through the normal
empty-state UI, saves and previews those files, downloads both an initial and a
combined version, and verifies exact ZIP contents without changing the Git index. Built output under dist/ is also checked in the
browser with root-relative CSS and JavaScript module imports. A saved build wins
over an uncompiled source index; detected TypeScript/JSX entry points without a
saved build show a useful explanation while retaining all source tools.

An actual UI-started Hermes session changed the sample hero headline and captured
the result. Codex 0.167.0 then continued the same named path, read saved state through
`workgraph_read`, changed only Navigation, and preserved the hero byte for byte.
The chosen original direction stayed unchanged. Codex's write-tool approval was
preserved; the operator-owned launcher made its final source checkpoint. The machine
record is `/home/ali/.cache/workgraph/live-exploration-fixed/result.json`.

The live test exposed and corrected two integration gaps: Python module discovery
when an MCP host strips PYTHONPATH, and an all-actions tool forcing approval even
for inspection. The server now has an absolute entry, is required at startup, and
separates strictly read-only operations from mutation calls. Earlier blocked runs
remain in the local test history.

Claude Code uses the same MCP transport/launcher; this record does not claim a live
Claude model run. Framework app servers and external-service restoration are
outside the saved static preview contract. No revised demo should imply otherwise.

Verification uses actual temporary Git repositories. No tests reset the user's
working tree or staging index. The guided browser example discloses its scripted
edits and performs real core operations.

## Automated acceptance

`python -m unittest discover -s tests -v` covers persistent context, safe takeover,
exact dependency closure, outdated-input detection, reconciliation, alternatives,
immutable evidence, frozen checks, source-change rejection, timeout cleanup,
concurrent progress during checks, retry identities, publication recovery,
historical acceptance evidence, native adapter routing/deduplication, MCP protocol,
operator-only actions, CLI parsing, and local HTTP authentication/origin checks.

The original 1.0 suite contained 32 distinct tests. A separate review reproduced and
then rechecked the ownership, dependency-closure, tool-retry, publication-recovery,
sandbox-default, resume-binding, and selection edge cases.

## Browser acceptance

`tests/browser_acceptance.py` drives an isolated Chromium instance through the
complete visible example and creates work through the normal UI. It checks a
390-pixel mobile viewport for horizontal overflow and fails on browser errors.
It requires Playwright and Chromium as development tools, not runtime dependencies.

## Agent integration

`hermes plugins doctor /path/to/workgraph --ci` exercises the installed Hermes
manifest, runtime discovery, isolated import, and actual registration.

`tests/mcp_interoperability.py` uses the real Python MCP ClientSession SDK to
initialize the stdio server, discover its tool, checkpoint a real edit, replay a
request, and verify that an agent cannot call operator acceptance.

Native execution was additionally exercised through an actual Hermes 0.21.0
oneshot session on November 5, 2026. The session resumed an attached attempt,
created `native-proof.txt` through `write_file`, read it through a sandboxed
terminal command, and saved an explicit plan, decision, and open question.
Both tool operations have captured native receipts. The attempt finished paused;
the original checkout remained untouched. This live run is separate from the
scripted guided example and from Doctor's registration check. The machine-local
verification record is retained in the release production project.

The release also passed a clean wheel install and the complete terminal example
from outside the source checkout. Python 3.14.7/Git 2.55.0 were used for the core
suite; the real MCP client and Hermes runtime used Python 3.11.16.

## Scope

These checks establish the behavior exercised on the tested Linux environment.
They do not establish universal semantic conflict detection, arbitrary host-level
security, full hermetic execution, or superiority over every other VCS. The
comparative product claim is specific: Workgraph preserves and coordinates
unfinished work and its context/dependencies across the demonstrated transitions.
