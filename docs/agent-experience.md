# The complete Workgraph journey

## Opening is observational

“Open Workgraph” maps to tool action `workspace`, never the older `open` action
(which creates a work attempt). The portable server starts without binding to the
plugin checkout; its first request names an absolute project directory. Attached
sessions cannot switch projects. A per-project lock makes simultaneous opening
requests converge on one controller, with an authenticated identity check rather
than trusting a stale PID or a reused port.

The broker opens the operator URL directly in the local browser and returns only
a read-only viewing link to the model. Without a local display it returns that
viewing link. The browser moves the token out of the URL fragment immediately and
keeps it in local storage for that origin. The project access file has mode 0600.
This avoids accidental capability disclosure through conversation output; processes
running as the same local user remain inside the same OS trust boundary.

Opening does not create an attempt, choose a version, change a working directory,
rewrite files, or reconstruct a model conversation. Browser closure leaves the
controller and its tasks running. Multiple tabs see the same durable history.

## Browsing is separate from choosing

A moment opens a gallery, saved context, source/data capture summary, and independent
behavior results. The canvas supports pan, zoom, fit, a minimap, search, favorites,
and path filters. Mechanical branch-start saves are collapsed by default and can
be shown explicitly. The user's camera and selection persist locally; an operator
focus record lets the agent resolve “the version I’m looking at.”

Focus is browsing context, not edit authority. Choosing a direction marks a saved
point as preferred; it does not copy files into the user's checkout. Agent results
do not silently replace that preference. Publication stays in the engineering flow.

## Continuing creates an explicit task

The user chooses a saved point, gives a request, and selects an installed runtime.
A new direction restores exact source and configured SQLite snapshots. Continuing
the latest point may retain its named direction while giving the next worker a
fresh workspace and fencing the previous owner. Continuing an earlier point creates
a branch so later work is preserved.

The task sees explicit saved context and inherited protected behavior definitions.
The agent owns no operator capability and cannot rewrite the approved definitions
through Workgraph tools. The runtime retains its existing sign-in and approval
policy. Native Hermes captures supported foreground edits; portable managed
launches supply MCP and final capture. Optional trusted hooks add intermediate
milestones. Hidden reasoning, pending tool state, and context-window contents are
not transplanted between hosts.

The controller captures final work after stopping owned runtime process groups.
It then requests screenshots and protected-flow replays. A task completing is not a
passing check. Results show independently recorded evidence, failure, or a clear
not-checked state. Failed attempts and partial files remain recoverable.

## Browsers run disposable copies

An interactive app starts from immutable source and saved development data in its
own runtime. Each version has a separate loopback browser host, ticketed path, and
rewritten cookie namespace. Closing a dialog does not immediately destroy a copy;
returning within its idle lifetime keeps exploration state. Saved originals never
change. Explicit **Save interactions as a version** stops the app, snapshots its
SQLite data into a new branch, and queues fresh captures.

Record a behavior by performing steps, reloading if relevant, selecting expected
visible text, and naming the expectation. Password input is omitted. Recordings use
fresh copies for replay, so one test's created records do not contaminate another.
Visual expectations bind actual screenshot baselines and exact viewport dimensions.

## Reopening returns you to your place

`workspace` and `workgraph open` reuse the same project service. A closed browser
restores its selected moment, details state, and camera. Source/data history and
jobs live outside browser storage. A machine/controller restart keeps the same
access identity and prefers the prior port, with a fallback if occupied. Interrupted
captures are replayed; interrupted agent work is fenced and explicitly resumable.
The product does not label an abandoned worker's output complete.

## The boundaries we deliberately expose

Linux/bubblewrap and a locally installed Chromium are required for dynamic app
previews. Static source history remains useful without browser extras. External
services, framework-specific deployment platforms, streamed WebSockets, and
production database recovery are outside this developer preview. A source-only
older version is labeled code-only, rather than claiming an empty database is its
historical state. App connection requires an approved recipe; database imports
are explicit. The operator can always inspect source and download a source ZIP.
