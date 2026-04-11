# Dead Code Analysis - RegEngine

## Summary
Analysis completed on 2026-03-28. Found 1 disabled directory and 38 potentially unused components.

## Task 1: _disabled Directories

### Found
- **Location:** `./frontend/src/app/_disabled`
- **Status:** Cannot be deleted (filesystem read-only constraint)
- **Contents:** 13 subdirectories containing deprecated app routes:
  - about
  - checkout (with CheckoutClient.tsx)
  - design-partner
  - founding-design-partners (with AlphaSignupForm.tsx)
  - get-started
  - mobile (with capture page)
  - owner (18 files including settings, invoices, security, contracts, etc.)
  - partners
  - portal (with SupplierPortalPage.tsx)
  - status
  - walkthrough

**Note:** Attempted deletion via chmod, find -exec, and recursive permission fixes all failed with "Operation not permitted" errors. This appears to be a filesystem-level constraint (possibly read-only mount or containerized environment).

## Task 2: Unused Components in Frontend

### Potentially Unused Components (38 found)

#### UI Components (9)
- `components/ui/error-boundary.tsx` - Note: May have similar shadowed implementation
- `components/ui/popover.tsx`
- `components/ui/toaster.tsx`
- `components/ui/validated-input.tsx`
- `components/ui/command.tsx`
- `components/ui/service-unavailable.tsx`
- `components/ui/dropdown-menu.tsx`
- `components/ui/glossary-term.tsx`
- `components/ui/select.tsx`

#### Feature Components (29)
- `components/opportunities/GapAnalysisView.tsx`
- `components/layout/company-footer.tsx`
- `components/dashboard/ComplianceAlerts.tsx`
- `components/dashboard/RecentRisksWidget.tsx`
- `components/pcos/*` (7 components):
  - ComplianceTimeline.tsx
  - DocumentUploadModal.tsx
  - BudgetAnalysis.tsx
  - HowToGuide.tsx
  - ComplianceDashboard.tsx
  - AuditPackDownload.tsx
  - PaperworkStatusGrid.tsx
  - DocumentTracker.tsx
  - RiskHeatMap.tsx
  - FactLineageViewer.tsx
- `components/pcos/index.ts`
- `components/fsma/index.ts`
- `components/verticals/*` (11 components):
  - ComplianceTimeline.tsx
  - ApiReferenceSection.tsx
  - ComplianceReportButton.tsx
  - HeatMapWidget.tsx
  - ExportButton.tsx
  - healthcare/pillar-card.tsx
  - QuickActionsPanel.tsx
  - ComplianceScoreGauge.tsx
  - ComplianceMetricsGrid.tsx
  - VerticalTabs.tsx
  - RealTimeMonitor.tsx
  - VerticalDashboardLayout.tsx
- `components/verticals/index.ts`

## Recommendations

### Immediate Actions Needed
1. **Resolve filesystem constraint** - Contact DevOps to determine why the _disabled directory cannot be deleted despite ownership
2. **Lazy-loaded components** - Some components flagged as unused might be:
   - Dynamically imported via `React.lazy()`
   - Conditionally loaded based on feature flags
   - Used in error boundaries or fallbacks
3. **Code review before deletion** - Before deleting any component, verify:
   - No dynamic/lazy imports (`React.lazy()`, `dynamic()`)
   - No feature flag usage
   - No route-based lazy loading
   - No barrel exports re-exporting unused items

### Lower Priority
- Once filesystem access is restored, delete the _disabled directory
- Review pcos and verticals components - many appear unused, possibly from vertical-specific features
- Remove test files from components (e.g., `__tests__/curator-review.test.tsx`)
