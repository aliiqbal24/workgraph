# Workgraph 2.0 verification

Verification uses real local repositories, actual Chromium, real SQLite files,
and an actual Codex task. No model success text is counted as behavior evidence.

## Automated boundaries

- 69 core, regression, adapter, state-snapshot, and workspace tests pass. Added cases
  cover WAL/database-only history, exact branch/takeover restoration, path/symlink
  refusal, code-only legacy versions, operator/viewer capability separation,
  persistent browsing focus, project binding, and inherited immutable flow definitions, source stability across state backup, and actual image
  delivery through the read-only MCP tool.
- The V2 browser story passes: record a comment/save/reload expectation, protect it,
  replay it, save interactive data as a new version, preserve the original database
  and exact source, leave the chosen direction unchanged, reload into the same camera
  and selection, open the saved replay, and reject writes through a viewing link.
  Phone layout has no document overflow; no page errors occurred.
- A recorded expectation uses fresh test text. A deliberately broken descendant
  containing the old example text still fails that expectation. Existing data cannot
  supply the new replay's success text.
- The retained classic browser suite passes the original exploration stories,
  built CSS/modules, exact source ZIP content, preview isolation, and phone layout.
- All three channel ZIPs start MCP from extracted source outside the checkout with
  no ambient project binding. Initialization, two-tool discovery, and explicit-project
  read-only history pass. Portable manifests follow Agent Plugins 1.0 schemas.
- Claude Code's strict marketplace/manifest validator passes without findings.
  Installed Hermes Plugin Doctor passes discovery, import, and native registration.
  The installed Hermes CLI lacks the newer upstream catalog validator; public catalog
  CI remains a release gate rather than a claimed local pass.

## Actual feature adaptation

A UI-started Codex task borrowed the board layout from the deliberately broken
source into the focused target. It retained target filtering, eight development
issues, card links/test markers, and the target backend. Source and target originals
remain immutable. Only `client/app.js` changed in the adapted result; the target
SQLite snapshot is unchanged.

The browser controller independently replayed all three target protections on that
exact new code/data state: comments survive reload, new issues survive reload, and
High priority filtering keeps the intended issues. All three passed. The source
board independently fails its comment-persistence check. Closing the capture browser
did not stop the real task; the project controller completed and captured it.

A live Claude model run is not claimed. Earlier V1.1 native Hermes and Hermes-to-Codex
runs are retained separately. The V2 native adapter is checked through its public
registration surface and unit/regression coverage.

## Reproduce

```bash
python -m unittest discover -s tests -v
python tests/product_browser.py /tmp/workgraph-product-proof
python tests/studio_browser.py /tmp/workgraph-classic-proof
claude plugin validate . --strict
hermes plugins doctor . --ci
python scripts/package_release.py --output /tmp/workgraph-release
```

Browser scripts require Playwright/Pillow and Chromium. Source/dependency/state
fingerprints bind evidence to saved inputs; failed, interrupted, and unverified
states are explicit. Tests exercise this developer preview's supported workflows,
not universal compatibility with arbitrary applications or production services.
