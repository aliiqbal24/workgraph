# Agent integration

The native Hermes package is the hackathon entry. Codex and Claude Code adapters
use the same local core and stdio MCP contract. Workgraph owns no model keys.

## Deliberate agent actions

The `workgraph` tool supports open, status, resume, takeover, fork, checkpoint,
pause, reconcile, select, propose, inspect, verify, and diff. Acceptance, repository
initialization, and check configuration remain operator actions. Model-supplied
session IDs are not accepted; adapters use their runtime binding.

Native Hermes captures foreground terminal, write_file, and path-based patch
operations. It routes read_file and search_files into the same workspace. Guards
verify the routed paths and sandbox boundary before execution. An adapter exception
cannot silently authorize an unbound managed command. Tool execution and capture
are serialized per attempt, and persistent tool receipts deduplicate retries.

## Resume and handoff

Resume inspects saved code/context and attaches an active attempt only when its
session owner matches. Continuing another worker's saved attempt uses takeover.
The agent tool requires an active foreign owner to pause first; the operator UI
can explicitly transfer an active attempt. The old workspace is preserved and its
attempt cannot publish checkpoints after transfer.

Saved context distinguishes user objectives from agent notes. It is labeled data
when supplied to a new runtime. Permissions and credentials stay with the runtime.

## Launcher and lifecycle hooks

The launcher sets WORKGRAPH_REPO, WORKGRAPH_ATTEMPT, WORKGRAPH_SESSION, and
WORKGRAPH_RUNTIME. Each agent continues to authenticate through its own supported
mechanism. The launcher adds a local MCP server for Codex/Claude and checkpoints
the attached attempt on normal exit or interruption it observes.

Optional Codex and Claude hooks use SessionStart, PostToolUse, PreCompact, and
Stop; Claude additionally has PostToolUseFailure. Their configuration is printed
for review, never silently trusted. Hooks skip child sessions whose cwd differs
from the attached workspace. Separate child workers should receive separate
Workgraph launch/binding operations. Hosted tools and arbitrary background writes
are outside this hook capture contract.

The native Hermes adapter uses pre_llm_call and on_session_finalize; it does not
treat the end of each conversation turn as permanent session death. It works with
the installed v0.21.0 SDK and was checked with Plugin Doctor. Current catalog CI
is a separate admission check performed against the submitted pinned commit.

## Installation examples

After installing the Python package, a standalone MCP connection can use:

```json
{
  "mcpServers": {
    "workgraph": {
      "command": "/absolute/path/to/python",
      "args": ["-m", "workgraph", "--repo", "/absolute/path/to/repo", "mcp"]
    }
  }
}
```

Codex stores the equivalent connection under mcp_servers in its configuration.
The launcher supplies exact per-attempt/session arguments automatically. Use the
runtime's documented installer and hook trust UI; Workgraph supplies no trust
bypass flags.
