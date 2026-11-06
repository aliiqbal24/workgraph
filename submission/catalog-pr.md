Workgraph gives people a visible way to explore projects with agents: named saved
versions, exact-point branching, immutable static previews, side-by-side outcomes,
selected whole-file combinations, portable downloads, and continuation across
workers on one named path. Ordinary Git remains the source store.

The native plugin registers one workgraph tool, pre_tool_call, pre_llm_call,
on_session_finalize, and tool_request/tool_execution middleware. It bundles an
optional skill and uses public APIs. Codex/Claude use the same core through stdio
MCP; a strictly read-only tool separates inspection from writes requiring approval.

Validation: 56 automated tests, full Chromium story flows, own dirty-project start
and exact archive export, real MCP SDK interoperability, clean wheel install and
complete engineering example, Hermes Plugin Doctor, actual native execution, and
an actual UI-started Hermes-to-Codex continuation. The headline from Hermes stayed
byte-identical when Codex changed only Navigation on the same named path.
A live Claude model run is not claimed. This PR's catalog CI remains the admission
validation; the installed Hermes exposes Doctor rather than plugins validate.

Disclosures: reads/writes selected repositories and managed workspaces; invokes
Git, local agent CLIs, and approved foreground commands; stores source, explicit
context, task output, check logs, events, and receipts locally; serves an optional
token-authenticated localhost UI. Runtime authentication/approvals stay intact.
Normal runtime commands may use the network; checks use a private network
namespace. No telemetry, credential-store access, self-updater, or core patches.

Linux/bubblewrap required by default. Preview is saved static regular files;
framework servers and external services are not started. Combinations are explicit
whole-file replacements/deletions, with provenance and originals preserved. The
demo discloses its scripted sample variants and separately shows saved results
from the verified actual agent runs.
