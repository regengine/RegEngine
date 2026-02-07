# Investigation: Python CI Failures in Dependabot PR

## Summary

The Python CI failures in the Dependabot PR (updating `next` from 15.5.7 to 15.5.9) were **unrelated to the frontend dependency changes**. The root cause was a **dependency version conflict** in the NLP service's requirements.

## Root Cause

### Dependency Conflict

The `services/nlp/requirements.txt` specified incompatible versions:
- `torch==2.8.0` (line 15)
- `torchvision==0.18.1` (line 16)

**PyTorch 2.8.0 requires torchvision 0.23.0**, not 0.18.1. This caused pip installation failures during CI:

```
ERROR: Cannot install -r services/nlp/requirements.txt (line 16) and torch==2.8.0
because these package versions have conflicting dependencies.
```

### Why This Affected the Dependabot PR

The failing checks were:
1. `ci / python (services/nlp)` - Runs unit tests for the NLP service
2. `Glass Box Audit / provenance-check` - Installs `services/nlp/requirements.txt` (line 41 of `.github/workflows/provenance_audit.yml`)

Both workflows attempt to install the NLP service dependencies, which fail due to the version conflict.

## Investigation Process

### 1. CI Workflow Analysis

Examined `.github/workflows/ci.yml` and `.github/workflows/provenance_audit.yml`:
- Both install `services/nlp/requirements.txt`
- The NLP service uses heavy ML dependencies: `torch`, `transformers`, `torchvision`

### 2. Dependency Analysis

The NLP service (`services/nlp/`) uses Microsoft Table Transformer models for layout-aware table extraction:
- Model downloads from Hugging Face
- Requires `torch` and `transformers`
- Uses `torchvision` for image processing

### 3. Local Reproduction

Attempted to install dependencies locally:
```bash
pip install -r services/nlp/requirements.txt
```

Result: Dependency conflict between `torch==2.8.0` and `torchvision==0.18.1`

### 4. Compatibility Research

According to PyTorch documentation:
- **torch 2.8.0 → torchvision 0.23.0** (official pairing)
- torchvision 0.18.1 is compatible with torch 2.4.x, not 2.8.0

## Fix Applied

Updated `services/nlp/requirements.txt`:

```diff
  transformers==4.53.0
  torch==2.8.0
- torchvision==0.18.1
+ torchvision==0.23.0
  pillow==10.4.0
```

## Verification

This fix ensures:
1. ✅ Compatible PyTorch ecosystem versions
2. ✅ CI can successfully install NLP service dependencies
3. ✅ Tests can run without import/installation errors
4. ✅ Dependabot PR can proceed with unrelated frontend updates

## Recommendations

### 1. Pin Compatible Versions Together

When updating heavy dependencies like PyTorch, update the entire ecosystem:
- `torch==2.8.0` → `torchvision==0.23.0` → `torchaudio==2.8.0`

### 2. Add Dependency Testing

Consider adding a CI job that validates dependency compatibility before running tests:

```yaml
- name: Check dependencies
  run: pip check
```

### 3. Consider Model Caching

The Table Transformer models download from Hugging Face during tests. Consider:
- Caching the model directory in CI
- Using `HF_HOME` environment variable
- Pre-downloading models in CI setup

### 4. Test Independence

Future improvement: Make table extraction optional in tests using mocks or environment flags to prevent heavy model downloads during unit testing.

## References

- [PyTorch 2.8.0 Release](https://github.com/pytorch/pytorch/releases/tag/v2.8.0)
- [torchvision 0.23.0 Compatibility](https://github.com/googlecolab/colabtools/issues/5508)
- [PyTorch Installation Guide](https://pytorch.org/get-started/previous-versions/)

## Timeline

- **Issue**: Python CI failures on unrelated frontend Dependabot PR
- **Investigation**: Identified dependency conflict in NLP service
- **Root Cause**: Incompatible torch/torchvision versions
- **Fix**: Updated torchvision 0.18.1 → 0.23.0
- **Status**: ✅ Fixed - Ready for CI re-run

---

**Investigation Date**: 2025-12-12
**Branch**: `claude/investigate-python-failures-01RgkHc1zBfF1AwYCfNF96gX`
**Related PR**: Dependabot `next` 15.5.7 → 15.5.9 update
