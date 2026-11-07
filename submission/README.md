# Workgraph submission — 2.0

**Explore freely. Keep what works.**

An agent can improve a screen and quietly break the behavior underneath. Workgraph
makes exploration reversible at the product level: a branching tree of recognizable
saved source, development data, and explicit context, with actual galleries and
independently recorded behavior evidence.

## Submission description

Open Workgraph from Hermes, Codex, or Claude Code. Browse a saved product without
changing the conversation. Continue from its exact state in a separate direction.
Record what should keep working, then let those expectations follow future branches.
Compare directions and ask an agent to borrow just the feature you want. Keep both
originals and verify the new result against the target's protected behaviors.

This developer preview adds SQLite development-state snapshots, real isolated app
previews, desktop/phone galleries, recorded checks, visual expectations, semantic
borrow/undo tasks, and a persistent project controller. Closing the tab leaves tasks
running; reopening restores your place. Git remains the source storage and checked
publication layer underneath.

## What the demo proves

The 102-second narrated walkthrough shows actual UI operations with Relay, an
original animated AI presenter. It shows seven versus eight saved issues, recording
a reload/persistence expectation, a deliberately broken board's failed browser
replay, and a real Codex-adapted board that keeps the target filter, eight issues,
and reliable comments. All three target protections independently pass on the new
saved state. Only `client/app.js` changed; target database blobs are byte-identical.

The initial sample directions/regression are scripted and disclosed. The Codex run
is real, and the footage labels its result as saved rather than staging execution.
The product, app instances, SQLite snapshots, images, and checks are real. The new
production is in `/home/ali/Videos/workgraph-v3/`; earlier deliveries remain intact.

## Validation

69 core/interface/regression tests, the V2 browser story, the retained classic browser
suite, repeated open and immediate stop/reopen, actual screenshot delivery to MCP,
clean unpacked source MCP across all three packages, strict Claude validation, and
native Hermes Plugin Doctor. See [the evidence](../docs/verification-v2.md).

Live Claude model execution and current upstream Hermes catalog CI are not claimed.
The installed older Hermes CLI lacks the new catalog `validate` command. Public
review/hosting remain separate release steps.

Release source pin: `37c7280a514d3fa23e7193f44b5123d1f9c90163`.

## Install and publication

[README](../README.md) has local setup and host integration commands.
[Publication](../docs/publication.md) describes the direct-release, Hermes catalog,
Claude marketplace, and Codex local-plugin routes and their current review gates.
The proposed public repository is `aliiqbal24/workgraph`; it does not yet exist.

The GitHub app connector currently needs reauthentication; the existing GitHub CLI
is signed in to `aliiqbal24`. No public repository, release, catalog PR, social post,
or hackathon entry has been sent. Release files are prepared locally so publication
can be the next concrete action after confirming the public destination.
