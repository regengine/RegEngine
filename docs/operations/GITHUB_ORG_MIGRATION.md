# GitHub Org Migration Record

Completed: 2026-04-28

Current ownership:

- GitHub org: `regengine`
- Main repo: `regengine/RegEngine`
- Simulator repo: `regengine/inflow-lab`

## Completed Steps

1. Created the `regengine` GitHub organization.
2. Transferred `PetrefiedThunder/RegEngine` to `regengine/RegEngine`.
3. Transferred `PetrefiedThunder/regengine_codex_workspace` to the org.
4. Renamed the simulator repo to `regengine/inflow-lab`.
5. Updated RegEngine's Inflow contract workflow to target:

```yaml
INFLOW_LAB_REPOSITORY: regengine/inflow-lab
```

## Verification

```bash
gh repo view regengine/RegEngine --json nameWithOwner,url,defaultBranchRef
gh repo view regengine/inflow-lab --json nameWithOwner,url,defaultBranchRef
git ls-remote https://github.com/regengine/RegEngine.git HEAD
git ls-remote https://github.com/regengine/inflow-lab.git HEAD
```

## Follow-Up Audits

Historical audit docs may still contain old `PetrefiedThunder/RegEngine`
issue links. GitHub redirects those links after transfer, so they do not
need bulk rewriting unless a document is product-facing or actively used
by automation.

For active references, use:

```bash
rg -n "PetrefiedThunder/regengine_codex_workspace|regengine_codex_workspace|PetrefiedThunder/RegEngine" .
```
