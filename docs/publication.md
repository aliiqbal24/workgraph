# Publication route — 2.0

Workgraph is public and directly installable. The catalog listing is awaiting
maintainer review; it is not yet an accepted marketplace entry.

- [Public source](https://github.com/aliiqbal24/workgraph)
- [Installable 2.0.0 release](https://github.com/aliiqbal24/workgraph/releases/tag/v2.0.0)
- [Hermes catalog PR](https://github.com/NousResearch/hermes-agent/pull/150453)
- [Current upstream Hermes admission validation: passed](https://github.com/aliiqbal24/workgraph/actions/runs/42331776805)
- [69-test acceptance run: passed](https://github.com/aliiqbal24/workgraph/actions/runs/42331776985)

The immutable release source is
`37c7280a514d3fa23e7193f44b5123d1f9c90163`. Main can continue to change while
users test this fixed version. Functional updates get a new version and release,
followed by an updated exact catalog pin. Never move the published tag.

## The fastest useful release

The release includes a wheel, three plugin ZIPs, checksums, verification metadata,
and a narrated product walkthrough. The wheel was downloaded from the public
release, checksum checked, and installed into the local runtime. The native Hermes
plugin was installed from the public repository at the exact release commit. A
real task through that installation completed with three independently passing
browser checks. Fresh Hermes tool discovery also opened the same project.

Claude's marketplace is public in the same repository and has been installed from
GitHub locally. Codex's stdio MCP integration is configured locally. A live Claude
model run is not claimed. See [live testing](live-testing.md) for the actual workflow.

`python scripts/package_release.py --output /tmp/workgraph-release` produces explicit
Hermes, Codex, and Claude source packages and checksums. No environments, databases,
private controller files, recordings, bytecode, node_modules, or binaries enter
those packages. Browser dependencies are installed separately. Public portable
packages omit optional lifecycle hooks; native Hermes retains its declared public
hooks and middleware. Browser capture is optional; the stdio MCP server runs with
Python's standard library.

## Hermes catalog

The [official admission guide](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins/catalog-submission)
requires a public cloneable repository and a full 40-character SHA, then a PR adding
`plugin-catalog/workgraph.yaml` to `NousResearch/hermes-agent`. The listing is human
reviewed. Screenshots and all local commands/background/network behavior must be
disclosed. No runtime patching, built-in tool overrides, self-updater, or executable
payload is included.

The installed Hermes CLI's Plugin Doctor passes discovery, manifest import, and
registration. The current official upstream admission action also passed against
the exact public release. The open catalog PR adds only its pinned community entry;
catalog checks there run when a maintainer starts them. Local admission validation
does not imply catalog acceptance.

## Claude Code

The [official publication guide](https://code.claude.com/docs/en/plugins/publish)
supports a single-plugin repository with `.claude-plugin/marketplace.json` and source
`"./"`. Local manifest/marketplace validation runs with `claude plugin validate .`.
The public marketplace install is:

```text
/plugin marketplace add aliiqbal24/workgraph
/plugin install workgraph@workgraph-tools
```

Direct ZIP and `--plugin-dir` installation are also available. A broader
[Anthropic directory submission](https://claude.ai/directory/manage) is a separate
review. This product requires local execution and should be described for Claude
Code; a listing must not imply the local backend runs in a remote chat environment.

## Codex / OpenAI

The portable bundle uses the official [root plugin and MCP manifests](https://developers.openai.com/plugins/build/plugins).
Its stdio command invokes packaged source through `${PLUGIN_ROOT}`; no project path
is fixed at install time. Its first tool request explicitly selects the project.
Direct local installation/MCP setup is the immediate distribution route.

The [desktop-only submission rules](https://developers.openai.com/plugins/deploy/desktop-only)
currently restrict local MCP submissions to approved, allowlisted partners. That is
an external directory gate, not a reason to host users' repositories remotely or
promise an immediate public listing. Eligibility, a verified publishing identity,
clean desktop testing, and portal review are needed before that directory launch.
Do not misclassify this as a remotely executable plugin to bypass the local gate.

## Remaining hackathon steps

The [official announcement](https://ca.linkedin.com/company/nousresearch) requires
a catalog PR, a demo posted on X tagging `@NousResearch`, and both links through the
entry form. It specifies **under 90 seconds**, with a deadline of **November 11,
2026 at 5 PM EST** (3 PM in Edmonton). The form may be submitted once the PR is open;
marketplace acceptance need not precede that step.

The public source, release, and catalog PR are complete. User testing, the final
short demo post, and entry form remain. No social post or hackathon form submission
has been sent. Broader Claude/OpenAI directory applications are separate review
processes and are not claimed as complete.
