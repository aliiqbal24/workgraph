# Draft design for version control in the agent era

Prepared November 5, 2026.

The proposed system makes unfinished engineering work a durable, shared object. An agent can explore, stop, resume on another runtime, depend on another agent's work, and propose a combination for acceptance. The system preserves the relationship between the code, the instructions that authorized the work, the assumptions it used, and the evidence collected about it.

The central product hypothesis is that this relationship should remain coherent automatically as work proceeds. Agents and engineers should spend their attention on engineering decisions while the system maintains identity, isolation, recoverability, freshness, and publication rules.

The measure of success is useful work accepted per unit of human attention, at a comparable quality and compute budget. Fewer version control commands are useful only insofar as they improve that result.

The earlier prototype is an experiment, not a constraint on this design. No storage engine, command vocabulary, or implementation language is settled here.

## Research findings and their implications

Agent scale is already putting pressure on source control infrastructure. Anthropic reports that its merged changes grew from approximately 2,500 per day in May 2026 to over 30,000 per day in September. Its Scion system moves expensive operations to a service, uses content-addressed data and sparse materialization, and avoids requiring clients to maintain complete repositories. Anthropic also describes its workload as unusual. These results establish a scaling pressure at the frontier; they do not establish that every team needs a new storage engine. [Anthropic source control redesign](https://www.anthropic.com/research/redesigning-source-control)

GitLab is pursuing machine-scale source control, server-side access, and lifecycle context. A startup cannot assume that the established hosting platforms will remain focused on human workflows. The opportunity needs a more specific advantage than adding an agent API to repository hosting. [GitLab source control strategy](https://about.gitlab.com/blog/scaling-git-for-the-agentic-software-factory/)

Coordination also fails above the storage layer. Cursor reports agents mishandling locks and struggling with coordination even after an optimistic concurrency approach reduced some overhead. Cognition emphasizes that an action carries implicit decisions which another agent may not receive. The resulting design problem includes the assumptions agents share, rather than only the files they modify. [Cursor agent scaling research](https://cursor.com/blog/scaling-agents), [Cognition on context engineering](https://cognition.com/blog/dont-build-multi-agents)

Several attractive primitives already have substantial prior art:

| Existing system | Relevant capability | Implication for this design |
| --- | --- | --- |
| [Jujutsu](https://docs.jj-vcs.dev/latest/tutorial/) | Automatic working-copy snapshots, operation history, undo, and explicit conflicts. | Reliable recovery and convenient history operations are established expectations. |
| [GitButler](https://docs.gitbutler.com/ai-agents/overview) | Parallel branches and commands intended for agent workflows. | Improving the Git command surface alone is a narrow competitive position. |
| [Entire](https://entire.com/blog/entire-dispatch-0x0002) | Checkpoints associating agent context with code changes. | Saving conversations beside code is an existing category. |
| [Foremerge](https://foremerge.com/) | Shared intents, claims, dependencies, ChangeSets, and validation associated with candidate fingerprints. | Intent and evidence records alone do not distinguish a new product. |
| [AgentFS](https://turso.tech/blog/agentfs-overlay) | Copy-on-write isolation and captured filesystem modifications. | Cheap isolated execution is a component to evaluate, rather than an invention to claim. |
| [GitHub merge queues](https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/configuring-pull-request-merges/managing-a-merge-queue) | Required checks on proposed changes combined with the current target and earlier queued changes. | A clean merge followed by an integration failure is insufficient as the defining product demonstration. |

Pijul also demonstrates that changes, dependencies, and durable conflicts have a history beyond Git. A new design should distinguish its workflow and guarantees from the older ideas it builds upon. [Pijul change model](https://pijul.org/manual/why_pijul.html)

## The design premise

Git's immutable objects, content addressing, inspectable history, and distributed ownership remain valuable. The strongest redesign changes the objects agents manipulate and the responsibilities the system assumes around those objects.

Today an engineer often connects several separate sources of truth: an issue describes the goal, a conversation contains decisions, a worktree contains edits, a branch contains selected snapshots, CI records some checks, and a pull request records review. The engineer or agent reconstructs the relationship between them whenever work moves or resumes.

The ideal system maintains those relationships as part of normal operation. A code tree becomes one materialized view of a larger history of work. Each view has an explicit basis, context, evidence, and publication status.

Git and additional services could represent much of this information. The product claim concerns the coherent system contract and user experience; the graph of Git commits is not inherently incapable of representing alternative histories. Whether a new storage engine is justified is a later question about scale, semantics, and compatibility.

The proposed distinguishing experience is continuous coherence across the whole lifecycle: work remains resumable, dependencies remain identifiable, assumptions can become outdated visibly, and acceptance always identifies precisely what was accepted. The individual mechanisms have prior art; the integrated experience must earn its advantage through measured results.

## What changes in the agent era

An agent can produce drafts faster than a person can organize or review them. Several agents may explore alternatives to the same problem. A single useful change may outlive its original conversation, model, machine, or context window. Agents can repeat operations after an uncertain result, continue from outdated assumptions, and report success without sufficient evidence.

These conditions favor cheap private experimentation, automatic capture, explicit ownership of mutable state, portable handoffs, and an acceptance process whose rules are enforced independently of the implementation agent.

They also create a resource problem. Retaining every observation forever, testing every combination, and propagating every update to every agent would consume enormous storage, compute, and attention. The ideal therefore includes selective materialization, explicit retention, reusable evidence where its inputs are controlled, and focused notifications.

The system should scale downward as well. One engineer using one agent should receive useful recovery and handoff behavior without operating a collaboration platform.

## The objects the system should expose

These are conceptual objects rather than a proposed database schema.

| Object | Meaning | Important property |
| --- | --- | --- |
| Work | A purposeful change with an authorized objective and constraints. | Its identity survives sessions and implementation revisions. |
| Attempt | One path of exploration for that work. | Mutable execution belongs to a specific attempt and view. |
| Revision | An immutable checkpoint of implementation and explicit saved context. | Later edits create a successor rather than altering the checkpoint. |
| View | An exact composition of revisions and captured execution inputs. | Agents and checks can identify which world they observed. |
| Evidence | An attributed observation about a specific view. | Its applicability can be evaluated without trusting a success statement. |
| Decision | A choice such as selecting an approach or accepting a proposal. | Its authority and scope are explicit and versioned. |

Dependencies connect exact revisions and inputs. A work item may be split or combined, with lineage preserved. A large user objective can span several work items. A session can participate in multiple work items, while each mutating operation still has an unambiguous attempt and workspace.

The objective itself can evolve. Changing what a piece of work is supposed to achieve must leave an explicit record and trigger reconsideration of any evidence or approval whose meaning depended on the earlier objective.

The system should distinguish three kinds of statements: an agent claimed something, a runner observed something, and an authorized person or policy approved something. A saved explanation is useful context; it does not become a verified fact merely because it was saved.

Context must also preserve its authority. User instructions, project policy, agent notes, and untrusted tool or repository content cannot become interchangeable when saved and restored. A handoff must not promote an instruction found in an artifact into an authorized directive.

## Private exploration and accepted software

Exploration should be persistent by default. An agent can try a design, checkpoint it, branch an alternative, compare the results, or give the attempt to another agent. Failed approaches remain discoverable under the retention policy, including their failure evidence and explicitly recorded reasons for stopping.

Capturing ordinary progress should be automatic. The agent should make deliberate decisions about trying an alternative, changing scope, or proposing work. It should not repeatedly decide which files to stage or how to preserve its progress before a context reset.

The default interaction should be small: attach to a piece of work, use ordinary editing and execution tools, and propose an outcome. Forking and handing off are available when useful. Routine capture and state bookkeeping should not require the agent to narrate every action into additional tool calls. Expensive interpretation can enrich the record asynchronously; preserving a checkpoint should not depend on a model successfully interpreting it.

A checkpoint binds the captured code to explicit context: the goal, current plan, decisions, unresolved questions, relevant artifact references, and applicable evidence. Original records remain addressable where retention and privacy policy permit; summaries are derived views. The product does not depend on access to hidden model reasoning.

The accepted history remains concise and intelligible. Experiments can contain broken intermediate states, while publication follows the project's policy. A team can inspect the full exploration behind an accepted change without turning its ordinary code history into a transcript of every tool call.

Retention must be visible. A promise that an acknowledged checkpoint is durable must identify what was captured and for how long. Secret material and unrelated personal state should remain outside automatic capture. Storage compaction must preserve the references and guarantees promised by the retention policy.

## Concurrency through coherent views

Each active attempt should work against an identifiable, coherent view. It can see accepted software plus selected speculative dependencies. Another agent's publication should not silently change files under a running command or make half of a dependency update visible.

At a safe boundary, the system can offer or apply an update according to policy. It should explain which relevant inputs changed, what evidence became outdated, and whether the agent's own edits still compose. An update that cannot be reconciled becomes a separate state the agent can inspect and resolve; unrelated work continues.

Sharing work should be cheap and distinct from accepting it. An agent should be able to depend on another agent's provisional revision without waiting for a human review or pretending that revision is already accepted.

Mutable attempt ownership needs stronger semantics than a name in a file. A takeover must prevent the old worker from continuing to write as the current owner. Advisory claims about engineering scope can help coordinate plans, but they should not be confused with enforcement of workspace ownership.

The system should avoid requiring every agent to copy a complete repository and its history. Views may materialize files on demand, and queries may operate directly on stored objects. Online collaboration can optimize sharing while local checkpoints remain useful during disconnection. Acceptance that requires shared agreement waits until that agreement can be established.

## Versioned assumptions and freshness

An agent's useful state includes assumptions about the software it read. For example, an implementation may assume a response includes a particular field, a migration has already been applied, or a policy allows a particular form of caching.

The system should record the basis of those assumptions where it can. It must distinguish explicit revision dependencies, declared contracts, mechanically derived dependencies, observed reads, and heuristic suggestions. These relationships have different strengths.

An observed file read is evidence of a dependency, but an absence of observed reads is insufficient to establish independence. Dynamic code, generated inputs, configuration, and external state can create hidden coupling. Selective invalidation is justified only where dependency coverage supports it. Otherwise the system must conservatively widen the affected scope.

When a relevant assumption changes, the system should mark the dependent work and its evidence accordingly and deliver a focused update to the agent. The agent can reconcile, fork, or withdraw the work. A silent reinterpretation of an old dependency as the latest revision would destroy the meaning of the record.

The goal is to prevent stale context from remaining invisible. The system can identify that a recorded assumption needs attention; it cannot automatically establish every semantic consequence of every change.

## Evidence and acceptance

Evidence should identify the code and composition checked, the definition of the check, the relevant environment and dependency inputs, the runner, the result, and its applicability. Where input coverage is incomplete or external state is mutable, that limitation affects reuse of the result.

Hermetic build systems already show why controlled inputs matter for reproducibility and caching. This design should reuse those principles and existing build infrastructure. A code hash alone does not identify all the inputs to a meaningful experiment. [Bazel on hermeticity](https://docs.bazel.build/versions/main/hermeticity.html)

Acceptance evaluates an exact proposal against current project policy. Required checks, reviewer authority, and the accepted base must still match at the moment of publication. A change after validation may require new evidence. The implementation agent must not satisfy a gate merely by changing the gate's definition or supplying a favorable narrative.

Checks provide evidence about the behavior they exercise. Textual conflicts can be identified mechanically. Broader interface conflicts can sometimes be detected by types, schemas, or contracts. Behavioral conflicts require relevant experiments, analysis, and judgment. The interface should make these distinctions visible rather than offering a universal green label.

Human review should focus on the intended behavior, constraints, architectural tradeoffs, observed evidence, and unresolved risks, with source diffs available for inspection. Routine publication can be delegated under a scoped policy. Novel changes and unresolved judgments still need an accountable decision maker.

Reversing an accepted change creates a new proposal against the current accepted state. The system should identify dependent work that may need reconsideration and preserve unrelated accepted work where the resulting composition permits it. Rewinding source does not undo emails, payments, deployed databases, or other external effects.

## Independent dimensions of state

A single status such as done conceals too much. The ideal keeps at least these dimensions separate:

| Dimension | Example states |
| --- | --- |
| Execution | Active, paused, interrupted, finished. |
| Publication | Private, shared, proposed, accepted, withdrawn, superseded. |
| Applicability | Current, outdated, conflicted, awaiting reconciliation. |
| Evidence | Missing, passing, failing, outdated, inconclusive. |
| Authorization | Unreviewed, approved within scope, denied, approval no longer applicable. |

A paused attempt can have passing evidence. A running attempt can depend on an outdated revision. A finished implementation can remain unapproved. The system should answer these questions directly without requiring an agent to infer them from a branch name.

## The experience an engineer should have

Consider an engineer asking for an API migration and the clients that use it.

An agent begins the API work. Another agent can start a client implementation against an explicit provisional API revision. A third explores a different migration approach. Each has an isolated view and persistent checkpoints.

The API agent stops unexpectedly. The engineer hands its work to a different runtime. The new session receives the captured code, objective, decisions, unresolved questions, dependency references, and applicable evidence. It can inspect the original artifacts behind the handoff. Runtime credentials and permissions do not transfer with the work.

The resumed agent revises the API. The client work remains available, and the system identifies that its recorded API dependency is outdated. It explains the relevant difference and marks affected evidence for reconsideration. The alternative migration attempt remains intact.

The engineer compares the alternatives using the evidence and tradeoffs, selects one, and reviews the resulting proposal. Acceptance identifies a precise composition. Existing code hosting receives an ordinary code change and a durable link to its work history.

The engineer's deliberate actions are choosing an objective, directing a tradeoff, selecting an approach, and approving an outcome. Routine preservation, workspace setup, and freshness bookkeeping happen as part of the system.

## Capabilities the ideal should make ordinary

Persistent, queryable work would enable interactions that currently require a collection of manual conventions:

- Ask for the smallest available composition that implements a particular outcome, with missing dependencies identified rather than silently omitted.
- Give two agents the same checkpoint to explore alternatives, then compare their observed behavior, cost, and explicitly recorded tradeoffs.
- Resume a promising attempt from another runtime while retaining a separate path for its original worker.
- Ask which current proposals relied on a contract that has just changed, with the basis and strength of each dependency visible.
- Inspect why an accepted design was chosen and retrieve the preserved alternatives and evidence that informed the choice.
- Construct a proposed future without a particular change, identify affected dependents, and test that future before deciding to publish it.

The system can provide structured retrieval and composition over recorded objects. Understanding an arbitrary outcome, finding every hidden dependency, or repairing the resulting code can require agent reasoning and new experiments. Those steps create attributed proposals and evidence rather than silently changing the canonical record.

## How it fits current agents

The core should have one shared work model, with adapters for each runtime. The model should remain useful if the user changes agents or code hosts.

Three integration surfaces serve different purposes. Tools expose deliberate actions such as opening work, forking, comparing, resuming, and proposing. Lifecycle events identify useful capture and context boundaries. A managed workspace or execution environment provides the actual isolation and state capture needed for stronger guarantees.

MCP is a portable interface for deliberate actions and queries. Installing an MCP server by itself does not intercept arbitrary filesystem writes, isolate a shell, or guarantee that all relevant events are captured.

### Hermes

A native Hermes plugin can expose work operations and attach lifecycle behavior. Its middleware can wrap tool execution. Its terminal environment provider interface offers a deeper integration for command, execute-code, and file-tool execution within an explicitly selected backend. These are suitable public surfaces for a hackathon entry that requires executable behavior. [Hermes plugin guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins), [Hermes middleware](https://hermes-agent.nousresearch.com/docs/developer-guide/middleware), [Hermes terminal environment providers](https://hermes-agent.nousresearch.com/docs/developer-guide/terminal-environment-plugin)

The proposed experience is automatic attachment of a session to work, isolated execution, checkpoints at completed tool boundaries, and a view of attempts, dependencies, and evidence. The adapter must preserve Hermes approvals and distinguish unfinished background execution from a completed checkpoint. Compatibility and capture coverage need explicit testing against the supported Hermes release.

### Codex

Official documentation describes MCP tools and lifecycle hooks including session start, tool use, compaction, and interruption boundaries. Session-start context can support a handoff and restoration of relevant context after compaction. Local tool hooks cover shell commands, apply_patch, and MCP calls; hosted tools have different coverage. [Codex MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli), [Codex hooks documentation](https://learn.chatgpt.com/docs/hooks)

The proposed adapter launches or attaches Codex within the selected workspace, exposes the common work operations, and uses supported hooks for capture and focused context updates. It should rely on managed execution for its strongest filesystem guarantees. A lifecycle hook that supplies context cannot by itself relocate every existing process or capture every hosted action. Portable plugin packaging can distribute the relevant tools and instructions where supported. [OpenAI plugin architecture](https://developers.openai.com/plugins/concepts/plugins)

### Claude Code

Claude Code exposes MCP and hooks for sessions, tools, compaction, and worktree creation. Its WorktreeCreate hook can replace the default creation behavior and return the isolated workspace path. The documented timing and coverage exceptions mean the adapter must choose a supported settings or launch path rather than assume every plugin hook runs before every workspace is created. [Claude Code hooks](https://code.claude.com/docs/en/hooks), [Claude Code MCP](https://code.claude.com/docs/en/mcp)

The proposed adapter maps those surfaces to the same work, revision, and view identities used by Hermes and Codex. Cross-runtime continuation restores captured engineering context and artifacts. It does not promise bit-for-bit continuation of a model's internal state.

### Shared compatibility rules

The common representation should identify goals, explicit decisions, artifact references, dependencies, and evidence independently of provider transcript formats. Runtime-specific raw records can remain optional attachments with access controls and retention rules.

Ordinary Git activity remains supported through explicit observation or import. The interface must distinguish imported or partially observed work from work executed under stronger managed guarantees. Existing credentials, review policies, and code-host protections remain authoritative.

## What dependable operation must mean

The reliability target is a set of precise invariants under defined failure conditions.

| Invariant | Required behavior |
| --- | --- |
| Durable acknowledgement | A checkpoint acknowledged as durable remains recoverable under its stated retention policy. |
| Exact identity | A revision identifies immutable captured content and context. |
| Isolation | One attempt cannot silently overwrite another attempt through the managed workspace boundary. |
| Safe takeover | A former owner cannot continue acting as the current writer after ownership transfers. |
| Retry safety | Repeating a request with the same operation identity does not create a second logical action. |
| Honest freshness | Evidence and approval retain their original scope; changed inputs cannot silently inherit them. |
| Atomic acceptance | Publication names one exact accepted proposal and respects the current acceptance conditions. |
| Recoverable uncertainty | A client can query the outcome after a timeout instead of guessing whether publication occurred. |
| Controlled degradation | An outage can leave private editing available while acceptance waits; the interface shows capture gaps explicitly. |
| Inspectable recovery | Crashes leave enough durable information to reconcile workspace, metadata, and publication state. |

Background processes require particular care. A completed tool response does not necessarily mean every child process has stopped writing. Checkpoints must declare their consistency boundary, and publication requires a stable captured candidate.

Reliability should not depend on a language model remembering to call a save tool, correctly classifying every shell command, or voluntarily enforcing the acceptance policy. Enforcement needs an execution and publication boundary the relevant worker cannot accidentally bypass.

These guarantees have a scope. Arbitrary host access can bypass a cooperative local tool. Complete behavior verification is limited by the checks and specifications available. Restoring captured source and context is different from restoring external services. The product should state its guarantees directly at these boundaries.

## Why adoption could be compelling

The strongest initial customer is a team running several agents across overlapping work in a repository they care about. Such a team can benefit from lower interruption costs, fewer repeated investigations, less manual reconciliation, and more reliable review context.

The individual developer needs immediate value too: reopening unfinished work without reconstructing it, trying alternatives without cleanup anxiety, and moving a task between runtimes. Collaboration should extend those benefits rather than being a prerequisite for them.

Adoption becomes compelling when useful accepted throughput rises while human attention and failure rates remain controlled. A product that only saves a few Git commands will compete with capable existing clients and improving agents. A product that lets a team run substantially more useful concurrent work with the same review capacity has a stronger economic position.

The relevant baseline is Git with good instructions, isolated worktrees, session recovery, CI, and a merge queue, plus current alternatives such as Jujutsu, GitButler, and Entire. GitButler's public benchmark is useful prior art for controlled evaluation of version control tasks, but a benchmark of those tasks does not by itself measure total engineering productivity. [GitButler benchmark](https://github.com/gitbutlerapp/version-control-bench)

The adoption path should preserve existing repositories, code hosting, CI, and ordinary inspection. A team should be able to use the product for one task, keep its accepted code, export its work records, and leave. Automatic capture and sensible defaults must carry most of the benefit; extensive manual metadata entry would recreate the coordination burden.

No design can establish inevitable adoption in advance. Small or largely independent workloads may remain well served by existing tools. The hypothesis is economic advantage for a growing class of concurrent agent workflows, and it needs comparative evidence.

## The company position to test

The proposed position is a neutral system for persistent engineering work across agents and code hosts. Its central responsibility is keeping the relationship between attempts, source, context, dependencies, evidence, and acceptance trustworthy.

Scheduling agents, choosing models, running arbitrary production workflows, and replacing all project management are outside that responsibility. The system can expose information those products need without owning their decisions.

A durable business would need advantages in reliability, integration quality, useful dependency and evidence relationships, and workflow adoption. An open format and credible export make adopting infrastructure safer. Neutrality across runtimes is useful, but incumbents can also implement interoperable interfaces; neutrality alone is insufficient protection.

Potential paid capabilities include shared work across a company, controlled publication, policy administration, large-scale materialization and evidence reuse, and integration with established infrastructure. The first plugin must demonstrate enough independent value to justify reaching that stage.

## The hackathon demonstration

The most distinctive first demonstration should show work surviving its original worker and staying coherent as its dependencies change.

1. Hermes starts a real task and another session starts dependent work against a named provisional revision.
2. The first session is interrupted after a durable checkpoint.
3. Another session resumes with the captured implementation, decisions, remaining questions, and evidence. A second runtime can be included if its adapter is genuinely ready.
4. The dependency changes. The system marks the dependent attempt and affected evidence as outdated, while preserving the work.
5. The agent reconciles the change, compares a preserved alternative, and proposes an exact candidate.
6. The human inspects the result and evidence; accepted code appears in the existing Git repository.

The demonstration should make the workspace and context transitions visible. It should show actual captured state and actual checks, with no claim that the system understands every semantic dependency or can restore an uncaptured external world.

A composition failure can support this demonstration, but the central result is continuity and coherence across interruption, alternative attempts, and changing assumptions. A full VCS rewrite, hosting service, or general semantic merge engine is unnecessary to establish that result.

## How to test superiority before committing to a product

Use representative tasks across several existing repositories and repeat them with one, several, and many concurrent sessions. Hold the model, task, check policy, and available compute comparable across treatments. Include interruption, takeover, dependency changes, and competing attempts rather than only successful branch manipulation.

Measure accepted correct work, human minutes spent managing state, repeated investigation, recovery time, compute cost, invalid evidence reuse, lost or misattributed work, and latency introduced by the system. Inspect results manually enough to establish that accepted output actually satisfies the tasks.

A proposed product bar is at least a twofold increase in accepted useful work per reviewer-hour on the targeted concurrent workloads, without a higher defect rate or a disproportionate compute bill. This is an ambition for evaluation, not a measured result. Smaller operational improvements may justify a useful tool while leaving the larger company thesis unproven.

Fault testing must separately exercise durable acknowledgement, duplicate requests, crashes at publication boundaries, stale owners, changing check definitions, partial connectivity, background writes, and interrupted synchronization. A compelling productivity result cannot compensate for a version control system that occasionally loses acknowledged work.

## Decisions to resolve before engineering resumes

The next design work should settle the product contract through concrete user journeys and failure cases.

First, choose the smallest unit of persistent work that remains understandable across sessions without forcing agents to maintain an elaborate task taxonomy. Second, define the exact state captured by a checkpoint and the guarantee attached to acknowledging it. Third, choose which dependency relationships can support authoritative invalidation and which remain advisory.

Then define the human review and acceptance experience, the minimum useful cross-runtime handoff, the treatment of ordinary Git edits, and the export and retention contract. The first release should make a small set of these promises dependable before expanding its authority.

The central design test is whether a user can start, interrupt, hand off, fork, reconcile, and accept real work while the system preserves its meaning and state. That experience, measured against the strongest existing workflows, should decide whether this becomes a new version control product or a narrower integration.
