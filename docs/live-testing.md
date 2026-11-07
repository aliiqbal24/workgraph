# Test and demo the installed product

The installed plugin and CLI are the product. The app project you work on is a
separate Git repository. Keep plugin development separate so a source edit cannot
silently change the version you are demonstrating.

## First run

Install the native Hermes plugin from the public release pin in the release notes,
then enable it. Install the browser-enabled CLI from the checkout or released wheel
as described in the README. Chromium and bubblewrap must be available on Linux.

Create an actual full-stack project and open its workspace:

```bash
workgraph showcase --directory /absolute/path/to/my-workgraph-test
```

That command creates Fieldwork, a real Python/SQLite issue tracker with saved
source/data versions. Its initial example directions are scripted and disclosed.
Your subsequent agent tasks, snapshots, browser checks, and edits are live.

Start Hermes in that project, binding only this process to it:

```bash
cd /absolute/path/to/my-workgraph-test
WORKGRAPH_REPO="$PWD" hermes
```

Then ask:

> Open Workgraph for this project. Show me its saved directions.

This opens the same workspace without creating a work attempt. Browse in the UI,
then give the agent an explicit edit request such as:

> Branch from the focused version. Give the app a new title, keeping the filters,
> saved issues, and comment persistence. Save the result with a clear name.

Alternatively use **Continue from here** in the UI and choose Hermes. It launches a
focused task with the normal Hermes permissions and your existing sign-in. Results
appear on the tree. A completed model task and passing behavior checks are separate.

## A five-minute real demo

1. Open the project from Hermes. Browse an earlier and later data state.
2. Open a version's actual app and inspect its desktop/phone screenshots.
3. Record a comment, reload, select the text that should remain, and protect it.
4. Compare the broken board with the focused list. Ask your configured agent to
   borrow the board while preserving the target's filters, data, and behaviors.
5. Wait for the actual task and independent checks. Open the result and its replay.
6. Close the browser tab. Ask Hermes to open Workgraph again; return to the same
   project and saved point. Closing the tab does not stop tasks.

Use fictional development data. A live app copy is disposable until you choose
**Save interactions as a version**. Your source project and preferred version remain
available. `workgraph stop` explicitly stops the project's local controller.

## Editing Workgraph itself

Keep using the installed release while editing the plugin checkout. For an isolated
source build, use a separate Python environment and Git worktree. Do not replace a
published release tag or silently change installed files. When ready, increment the
version, run the relevant checks, release it, and update the exact catalog pin.
