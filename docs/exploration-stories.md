# Stories for exploring projects with agents

The product should make it safe and understandable to explore different versions
of a project. A person chooses a visible outcome; an agent receives an exact
saved starting point and its explicit context. The interface keeps inspecting,
continuing, choosing a direction, and publishing separate.

These are composite product scenarios, not interview transcripts. Their acceptance
criteria drive the implementation and browser checks.

## Find the version I liked

A founder asks an agent to improve a homepage. Several requests later, the new
page has lost the simplicity they liked. They remember the look, not a commit ID.
Reconstructing the old state from conversation or repeatedly asking the agent to
undo changes is slow and uncertain.

The ideal: scan a named visual history, open an earlier saved page, star it, and
make it the current direction. Later work remains available. Browsing history
does not interrupt a worker or overwrite files. Continuing makes a fresh workspace
from that exact point.

Acceptance: an older version renders its saved files; choosing it survives reload;
the newer version and its context still exist; the original checkout/index do not
change.

## Try another direction without losing this one

A designer likes the current page but wonders whether an editorial or colorful
direction would work better. A single conversation encourages serial edits,
manual copies, and uncertainty about which state a new request starts from.

The ideal: choose any saved point and create named paths from it. Each gets its own
workspace and saved context. The original stays current until the person chooses
otherwise. An agent can work on a selected path while the person explores another.

Acceptance: two paths share the exact selected parent, edits in one do not enter
the other, the graph shows their ancestry, and repeated requests do not duplicate
paths.

## Compare outcomes rather than commit messages

A person has two versions and cannot decide from summaries or source diffs.
Switching the same checkout/dev server repeatedly makes comparison tedious.

The ideal: put two saved pages side by side, switch between desktop and phone
width, and see the actual changed files when useful. Each preview identifies its
version. The running worker's files cannot change either saved preview.

Acceptance: side-by-side frames render different immutable trees; changing a
workspace after saving does not change those previews. Non-web projects get a
clear file comparison instead of a fabricated preview.

## Keep this part from the other direction

A person prefers one layout and the navigation from another. Choosing one whole
branch discards useful work; asking an agent to recreate the part from memory is
unreliable.

The ideal: inspect which files differ, bring selected files into a new combined
path, and preview it before choosing it. Both source versions remain available,
and provenance records which source supplied each file. A semantic request that
does not correspond to whole files belongs to an agent task with both versions
identified, rather than an automatic promise to understand arbitrary features.

Acceptance: chosen files come from the selected source, all other target files
remain byte-identical, deletion is explicit, source versions remain unchanged,
and previous passing evidence is not attached to the new version.

## Continue here with another agent

A session ends or a person wants another model's approach. The desired starting
point is an earlier version, not necessarily the latest checkout or conversation.

The ideal: select the version, choose a runtime, give the next instruction, and
start a new isolated path from the interface. The next worker gets saved code,
decisions, and questions plus the current request. Its progress and outcome appear
on that path; errors remain visible and its partial work remains recoverable.

Acceptance: the runtime starts in the exact managed workspace, receives labeled
context, cannot silently replace the chosen direction, and produces real saved
revisions. Cancellation preserves files. Runtime authentication and normal host
approvals remain in force.

## Product boundaries

Static web projects with an index.html entry get isolated saved previews. This
release does not execute arbitrary package installation, application servers,
database migrations, or external services just to browse a historical version.
Other projects can still use the version graph, file comparison, branching,
selected-file combination, context and agent continuation.

Automatic saves capture file/source state and explicit notes, not hidden model
state or external effects. File combination is explicit replacement/deletion,
not a universal semantic merge. Choosing a direction does not publish it; the
existing independently checked acceptance workflow remains available separately.

Checkpointing and branching already exist in current agent products. The
hypothesis is that their combination with durable visual exploration, selected
recombination, and portable continuation can reduce the attention needed to work
with agents. That hypothesis needs real user use, not a novelty claim.

## Evidence and existing solutions

Claude documents specific limits on which files rewind captures, including files
changed through Bash. This supports making save coverage explicit rather than
promising that all agent checkpoint systems capture every file operation.
[Claude checkpoints](https://code.claude.com/docs/en/checkpointing#limitations)

Claude's session branching copies conversation state while existing background
work continues in the running process. A conversation fork and a separately
materialized code version are distinct actions.
[Claude session branching](https://code.claude.com/docs/en/sessions#branch-a-session)

GitButler explains the shared runtime state of parallel branches and recommends
separate worktrees for competing attempts. It also already provides visual history,
selective discard, cherry-picking and undo.
[GitButler parallel agents](https://docs.gitbutler.com/ai-agents/parallel-agents),
[selective discard](https://docs.gitbutler.com/commands/but-discard)

Cursor already supports best-of-n agent runs in isolated worktrees, comparison,
and applying a chosen result. Running alternatives and choosing a winner is not a
novel capability on its own.
[Cursor worktrees](https://cursor.com/docs/configuration/worktrees)
