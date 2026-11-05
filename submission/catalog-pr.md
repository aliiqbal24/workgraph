Workgraph preserves unfinished engineering work across agent sessions: isolated
attempts, explicit context, exact provisional dependencies, safe handoffs, and
checked candidates that export as ordinary Git commits.

The native Hermes plugin registers one `workgraph` tool, pre_tool_call,
pre_llm_call, on_session_finalize, and tool_request/tool_execution middleware.
It bundles an optional skill and uses public registration APIs only.

Validation: 32 unit/regression/interface tests, complete Chromium walkthrough,
real MCP SDK interoperability, clean wheel installation, installed Hermes 0.21.0
Plugin Doctor, and an actual native Hermes oneshot session with automatic file
and terminal capture. The local installation lacks the newer `plugins validate`
command; this PR's catalog CI is the admission validation.

Disclosures: reads/writes the selected repository/common Git directory and managed
workspaces; invokes Git and approved foreground shell/check processes; stores
source, explicit notes, check logs, events, and retry receipts locally; may serve
a localhost token-authenticated UI. Ordinary managed terminal commands retain
network access; checks use a private network namespace. No telemetry, credential
store access, self-updater, core monkeypatches, or approval bypasses.

Linux/bubblewrap required by default. The optional unsafe local operator override
is explicit and was not used for the demonstration. Semantic compatibility is
established only to the extent covered by configured checks. The guided demo's
edits are scripted and disclosed; repository operations are real. Native Hermes
execution was separately verified in an actual model session.
