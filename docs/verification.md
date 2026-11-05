# V1 verification

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

The current suite contains 32 distinct tests. A separate review reproduced and
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

Native execution capture must additionally be exercised through the installed
Hermes tool pipeline. Doctor alone proves registration, not execution behavior.
The release verification record and submission materials should distinguish those
checks from any live model run.

## Scope

These checks establish the behavior exercised on the tested Linux environment.
They do not establish universal semantic conflict detection, arbitrary host-level
security, full hermetic execution, or superiority over every other VCS. The
comparative product claim is specific: Workgraph preserves and coordinates
unfinished work and its context/dependencies across the demonstrated transitions.
