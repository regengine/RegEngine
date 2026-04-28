# GitHub Org Migration Runbook

Target state:

- GitHub org: `regengine`
- Main repo: `regengine/RegEngine`
- Simulator repo: `regengine/inflow-lab`

## Preconditions

- The GitHub account performing the transfer can create/manage the `regengine` org.
- The account has admin permissions on:
  - `PetrefiedThunder/RegEngine`
  - `PetrefiedThunder/regengine_codex_workspace`
- Local `gh` auth has org administration scope:

```bash
gh auth refresh -h github.com -s admin:org -s repo -s workflow
```

## Steps

1. Create the `regengine` organization in GitHub.
2. Transfer `PetrefiedThunder/RegEngine` to `regengine/RegEngine`.
3. Transfer `PetrefiedThunder/regengine_codex_workspace` to the org.
4. Rename `regengine/regengine_codex_workspace` to `regengine/inflow-lab`.
5. Update the Inflow contract workflow repository target:

```yaml
INFLOW_LAB_REPOSITORY: regengine/inflow-lab
```

6. Verify redirects and checkouts:

```bash
gh repo view regengine/RegEngine --json nameWithOwner,url,defaultBranchRef
gh repo view regengine/inflow-lab --json nameWithOwner,url,defaultBranchRef
git ls-remote https://github.com/regengine/RegEngine.git HEAD
git ls-remote https://github.com/regengine/inflow-lab.git HEAD
```

7. Audit public references:

```bash
rg -n "PetrefiedThunder/regengine_codex_workspace|regengine_codex_workspace|PetrefiedThunder/RegEngine" .
```

Update remaining references that are product-facing, docs-facing, or CI-facing.
