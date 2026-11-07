Workgraph makes agent-built products explorable through a local branching tree.
Saved versions can include SQLite development data, actual screenshots, and
independently replayed operator-approved behaviors. Users can continue from an
exact state or ask an existing agent to borrow a feature into a fresh branch.

Native surfaces: one registered tool, three declared observer hooks, and tool
request/execution middleware. No runtime monkey-patching or built-in tool override.
The native Plugin Doctor passes. The current upstream catalog validator and catalog
CI must pass against the final published 40-character pin before this PR is opened.

Disclosures:
- Reads/writes selected local Git projects and their common metadata, including
  explicit context, development snapshots, browser artifacts, and task logs.
- Executes Git, bubblewrap, Chromium/Playwright, approved app preparation/runtime
  commands, and operator-started Hermes/Codex/Claude subprocesses. Models retain
  their normal credentials, sign-in, and permission policy.
- Starts a persistent loopback-only project controller and separate disposable app
  processes; tasks may continue after browser closure. Explicit stopping preserves
  partial work. Source-only history works without optional browser dependencies.
- Approved preparation/app commands and existing agents can make normal network
  requests. The preview filesystem sandbox shares the host network. No telemetry,
  hosted repository service, model credential store, self-updater, or binary payload.
- Captures configured non-secret SQLite development data and screenshots. Password
  fields are omitted from recordings; other entered fixtures can be retained.

Attach the exact release screenshots and current narrated demo. Do not submit the
placeholder catalog pin; generate the entry from the final public commit.
