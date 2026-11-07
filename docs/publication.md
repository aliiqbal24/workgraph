# Publication route — 2.0

Prepared for a public developer-preview release, with source and separate plugin
bundles. Nothing is published by the packaging script. The proposed repository
from the earlier submission packet is `aliiqbal24/workgraph`; this checkout has no
remote, so the final owner/name and public release remain to be confirmed.

## The fastest useful release

Publish the reviewed source repository and attach the wheel, the three plugin ZIPs,
checksums, screenshots, and the current product demo to a GitHub release. People can
try the local product immediately and use their existing agent subscriptions.
Claude's marketplace lives in the same repository, so publishing that source makes
the marketplace available without waiting for directory review. Codex can use the
portable ZIP or the documented MCP command directly. Submit the Hermes catalog PR
in parallel with this direct-install release.

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

The installed Hermes 0.21 CLI has `plugins doctor`, which passes native discovery,
manifest import, and registration for this tree. It predates the current documented
`plugins validate --install-deps` command. Run that current upstream gate at the
published release pin before submitting; local doctor is not a substitute for catalog
CI. The prepared entry should be pinned only after the release commit exists.

## Claude Code

The [official publication guide](https://code.claude.com/docs/en/plugins/publish)
supports a single-plugin repository with `.claude-plugin/marketplace.json` and source
`"./"`. Local manifest/marketplace validation runs with `claude plugin validate .`.
After the repository exists, the user-facing install is:

```text
/plugin install workgraph --marketplace aliiqbal24/workgraph
```

Direct ZIP and `--plugin-dir` installation work before a directory listing. A broader
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

## Release sequence

1. Finish the release checks and generate artifacts from the exact reviewed tree.
2. Confirm the public repository destination, create it, and push the release/tag.
3. Attach immutable release artifacts and the demo; update install links from draft
   to live and verify a clean download/install.
4. Pin the Hermes catalog entry to the public commit and open its review PR.
5. Verify Claude marketplace installation from GitHub; pursue directory review in
   parallel. Use direct Codex installation while determining local-directory eligibility.
6. Submit the hackathon's required repository and demo links through its current
   entry form. The announcement/form requirements must be checked again at submission.

No release upload, catalog PR, social post, platform submission, or email is sent by
this document or by the build scripts.
