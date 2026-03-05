# Business Document Migration Plan

This document inventories files in the RegEngine repo that contain business-sensitive, investor-facing, sales, or pricing content. These files should be moved out of the public/shared engineering repo and into a private location before any external collaboration, open-sourcing, or investor due-diligence review of the codebase.

**Priority: Complete before the next investor conversation or any repo access grant to external parties.**

## File Inventory

### P0 — Confidential / Investor / Sales (move immediately)

| File | Content | Suggested destination |
|---|---|---|
| `RegEngine_Sales_Enablement_Kit.docx` | Sales deck (Word binary) | Google Drive / Notion |
| `RegEngine_TDD_Defense_Document.docx` | TDD defense (Word binary) | Google Drive / Notion |
| `partner_outreach_emails.md` | Confidential partner outreach templates | Private repo `regengine-biz` |
| `docs/PITCH_DECK.md` | Pitch deck content | Private repo `regengine-biz` |
| `docs/PRICING.md` | Pricing strategy | Private repo `regengine-biz` |
| `docs/POSITIONING.md` | Market positioning | Private repo `regengine-biz` |
| `docs/INVESTOR_DEMO_GUIDE.md` | Investor demo walkthrough | Private repo `regengine-biz` |
| `docs/internal/COMMERCIALIZATION_SUMMARY.md` | Commercialization strategy | Private repo `regengine-biz` |
| `docs/whitepapers/FAIR_LENDING_WEDGE_INVESTOR_NARRATIVE.md` | Investor narrative | Private repo `regengine-biz` |
| `docs/specs/FAIR_LENDING_COMPLIANCE_OS_MVP_SPEC.md` | Non-FSMA vertical spec | Private repo `regengine-biz` |
| `docs/security/SOC2_FAIR_LENDING_CONTROL_MAPPING.md` | SOC2 control mapping for fair lending | Private repo `regengine-biz` |

### P1 — Sales Enablement Directories (move as batch)

| Directory | Content | Suggested destination |
|---|---|---|
| `sales/` | Cold outreach templates, investor brief, supplier one-pager | Private repo `regengine-biz` |
| `sales_enablement/` | Full sales kit, TCO calculators (10 verticals), pricing, whitepapers (33 files) | Private repo `regengine-biz` |
| `docs/whitepapers/` | Industry whitepapers, PDF export tooling | Private repo `regengine-biz` |

### P2 — Multi-Vertical Specs (move to prevent scope signaling)

| File/Directory | Content | Suggested destination |
|---|---|---|
| `docs/MULTI_INDUSTRY_EXPANSION.md` | Expansion roadmap | Private repo `regengine-biz` |
| `docs/compliance/ingestion_library/` | Compliance specs for 7+ industries | Private repo `regengine-biz` |
| `docs/finance_dashboard_spec.md` | Finance vertical dashboard spec | Private repo `regengine-biz` |
| `docs/PRODUCT_ROADMAP.md` | Full product roadmap | Private repo `regengine-biz` |
| `docs/SPRINT_PLAN.md` | Sprint plan | Private repo `regengine-biz` |

### P3 — Internal Engineering Docs (move or keep private)

| File/Directory | Content | Suggested destination |
|---|---|---|
| `docs/internal/` | Internal status, implementation summaries | Keep if repo stays private; move if repo becomes public |
| `docs/content/the-handoff-problem.md` | Content marketing draft | Private repo `regengine-biz` |
| `docs/internal/portfolio_case_study.md` | Portfolio case study | Private repo `regengine-biz` |

## Migration Steps

### 1. Create private destination repo

```bash
gh repo create PetrefiedThunder/regengine-biz --private --description "RegEngine business docs, sales enablement, and investor materials"
```

### 2. Copy files to the private repo

```bash
# Clone the new repo
git clone git@github.com:PetrefiedThunder/regengine-biz.git ../regengine-biz

# P0 files
cp RegEngine_Sales_Enablement_Kit.docx ../regengine-biz/
cp RegEngine_TDD_Defense_Document.docx ../regengine-biz/
cp partner_outreach_emails.md ../regengine-biz/
cp docs/PITCH_DECK.md ../regengine-biz/
cp docs/PRICING.md ../regengine-biz/
cp docs/POSITIONING.md ../regengine-biz/
cp docs/INVESTOR_DEMO_GUIDE.md ../regengine-biz/
cp docs/internal/COMMERCIALIZATION_SUMMARY.md ../regengine-biz/
cp docs/whitepapers/FAIR_LENDING_WEDGE_INVESTOR_NARRATIVE.md ../regengine-biz/
cp docs/specs/FAIR_LENDING_COMPLIANCE_OS_MVP_SPEC.md ../regengine-biz/
cp docs/security/SOC2_FAIR_LENDING_CONTROL_MAPPING.md ../regengine-biz/

# P1 directories
cp -r sales/ ../regengine-biz/sales/
cp -r sales_enablement/ ../regengine-biz/sales_enablement/
cp -r docs/whitepapers/ ../regengine-biz/whitepapers/

# P2 files
cp docs/MULTI_INDUSTRY_EXPANSION.md ../regengine-biz/
cp -r docs/compliance/ingestion_library/ ../regengine-biz/compliance-ingestion-library/
cp docs/finance_dashboard_spec.md ../regengine-biz/
cp docs/PRODUCT_ROADMAP.md ../regengine-biz/
cp docs/SPRINT_PLAN.md ../regengine-biz/

# Commit and push
cd ../regengine-biz
git add -A
git commit -m "Initial migration of business docs from RegEngine repo"
git push -u origin main
```

### 3. Remove files from the engineering repo

```bash
cd /path/to/RegEngine

# P0
git rm RegEngine_Sales_Enablement_Kit.docx
git rm RegEngine_TDD_Defense_Document.docx
git rm partner_outreach_emails.md
git rm docs/PITCH_DECK.md
git rm docs/PRICING.md
git rm docs/POSITIONING.md
git rm docs/INVESTOR_DEMO_GUIDE.md
git rm docs/internal/COMMERCIALIZATION_SUMMARY.md
git rm docs/whitepapers/FAIR_LENDING_WEDGE_INVESTOR_NARRATIVE.md
git rm docs/specs/FAIR_LENDING_COMPLIANCE_OS_MVP_SPEC.md
git rm docs/security/SOC2_FAIR_LENDING_CONTROL_MAPPING.md

# P1
git rm -r sales/
git rm -r sales_enablement/
git rm -r docs/whitepapers/

# P2
git rm docs/MULTI_INDUSTRY_EXPANSION.md
git rm -r docs/compliance/ingestion_library/
git rm docs/finance_dashboard_spec.md
git rm docs/PRODUCT_ROADMAP.md
git rm docs/SPRINT_PLAN.md

git commit -m "chore: remove business docs migrated to regengine-biz"
```

### 4. Scrub from git history (important)

Simply deleting files leaves them in git history. If anyone with repo access runs `git log --all --full-history -- docs/PRICING.md`, they can recover the content. Use `git filter-repo` to purge:

```bash
pip install git-filter-repo

git filter-repo \
  --invert-paths \
  --path RegEngine_Sales_Enablement_Kit.docx \
  --path RegEngine_TDD_Defense_Document.docx \
  --path partner_outreach_emails.md \
  --path docs/PITCH_DECK.md \
  --path docs/PRICING.md \
  --path docs/POSITIONING.md \
  --path docs/INVESTOR_DEMO_GUIDE.md \
  --path docs/internal/COMMERCIALIZATION_SUMMARY.md \
  --path docs/whitepapers/ \
  --path docs/specs/FAIR_LENDING_COMPLIANCE_OS_MVP_SPEC.md \
  --path docs/security/SOC2_FAIR_LENDING_CONTROL_MAPPING.md \
  --path docs/MULTI_INDUSTRY_EXPANSION.md \
  --path docs/compliance/ingestion_library/ \
  --path docs/finance_dashboard_spec.md \
  --path docs/PRODUCT_ROADMAP.md \
  --path docs/SPRINT_PLAN.md \
  --path sales/ \
  --path sales_enablement/
```

After running `filter-repo`, force-push all branches:

```bash
git push --force --all
git push --force --tags
```

**All collaborators must re-clone after a history rewrite.** Coordinate this with the team.

### 5. Update README cross-references

After migration, remove or update these lines in `README.md` that reference moved files:

- `docs/specs/FAIR_LENDING_COMPLIANCE_OS_MVP_SPEC.md`
- `docs/security/SOC2_FAIR_LENDING_CONTROL_MAPPING.md`
- `docs/whitepapers/FAIR_LENDING_WEDGE_INVESTOR_NARRATIVE.md`

## What Stays in the Engineering Repo

These are engineering docs and should remain:

- `docs/ARCHITECTURE.md`, `docs/DEPLOYMENT.md`, `docs/OPERATIONS.md`
- `docs/ENV_SETUP_CHECKLIST.md`, `docs/LOCAL_SETUP_GUIDE.md`
- `docs/FSMA_RAILWAY_DEPLOYMENT.md`
- `docs/specs/FSMA_204_MVP_SPEC.md` (core product spec)
- `docs/security/INCIDENT_RESPONSE.md`, `docs/security/VDP.md`
- `docs/openapi/` (API schemas)
- `docs/architecture/` (C4 diagrams, ADRs)
- `docs/runbooks/` (operational runbooks)
- `CHANGELOG.md`, `CONTRIBUTING.md`
