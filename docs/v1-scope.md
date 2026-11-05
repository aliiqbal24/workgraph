# Workgraph V1 scope

V1 is complete when its local product, native Hermes adapter, portable agent tool,
operator UI, recovery flows, installation package, and reproducible example pass
the acceptance checks below. The wider ideal design remains a research direction.

| Capability | V1 behavior |
| --- | --- |
| Persistent work | An objective, constraints, alternatives, and saved explicit context survive a session. |
| Isolated attempts | Git-backed workspaces preserve the user's original checkout and index. |
| Checkpoints | Immutable source and context, explicit through tools and automatic in native managed Hermes foreground execution. |
| Handoff | A new workspace carries saved code and notes; the predecessor is fenced from new checkpoints. |
| Dependencies | Exact provisional revision pins; preferred-revision changes make dependent work outdated. |
| Reconciliation | A new attempt combines current dependencies with preserved implementation edits; conflicts remain explicit. |
| Candidates | Exact dependency closure, one version per work item, durable textual conflicts. |
| Evidence | Actual operator-defined checks, frozen source option, source-change rejection, timeouts, runner identity, historical acceptance basis. |
| Acceptance | Operator-owned, current required evidence, atomic Git publication, durable recovery journal. |
| Agent support | Native Hermes plugin; shared stdio MCP and local launch/hook bridges for Codex/Claude Code. |
| UI | Local authenticated Work, Review, and Timeline views with actual repository state. |
| Example | A disclosed guided example exercising interruption, handoff, dependency change, failed check, repair, and acceptance. |

V1 does not replace Git hosting, provide distributed synchronization, infer all
semantic dependencies, migrate hidden model state, undo external effects, or
provide a hostile-code multi-tenant sandbox. It targets Linux and requires
bubblewrap for its default managed terminal and check modes.

The submitted demonstration must use actual product state, identify scripted
example edits honestly, and demonstrate native plugin execution separately from
its registration check. It should explain the specific workflow improvement and
avoid unmeasured claims of universal superiority.
