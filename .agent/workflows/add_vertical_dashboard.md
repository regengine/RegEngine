---
description: How to add a new vertical dashboard to RegEngine application
---

# How to Add a New Vertical Dashboard

Follow this workflow to create a standardized web portal for a new industry vertical.

## 1. Create Directory Structure

Create the dashboard directory in `frontend/src/app/verticals/[vertical-name]/dashboard`.

```bash
mkdir -p frontend/src/app/verticals/[vertical-name]/dashboard
```

## 2. Create API Integration (`api.ts`)

Create `api.ts` in the dashboard directory.
- Define React Query hooks (`useQuery`) to fetch metrics.
- Mock data initially if backend is not ready.
- Use strict typing for all return values (e.g., `MetricConfig[]`, `SystemHealth`).

**Template:**
```typescript
import { useQuery, UseQueryResult } from '@tanstack/react-query';
import type { MetricConfig, SystemHealth, TimelineEvent, Alert } from '@/components/verticals';
// Import icons...

export const use[Vertical]Metrics = (): UseQueryResult<MetricConfig[]> => {
  return useQuery({
    queryKey: ['[vertical]', 'dashboard', 'metrics'],
    queryFn: async () => {
      return [
         // Define metrics...
      ];
    },
  });
};
```

## 3. Create Dashboard Page (`page.tsx`)

Create `page.tsx` using `VerticalDashboardLayout`.

**Requirements:**
- Wrapper: `<VerticalDashboardLayout title="..." icon={...}>`
- Components:
  - `<ComplianceMetricsGrid />`
  - `<ComplianceTimeline />` (Left col)
  - `<RealTimeMonitor />` (Right col)
  - `<QuickActionsPanel />`
  - `<ExportButton />`

**Template:**
```tsx
'use client';
import { VerticalDashboardLayout, ... } from '@/components/verticals';
import { use[Vertical]Metrics, ... } from './api';

export default function [Vertical]DashboardPage() {
  const { data: metrics, isLoading } = use[Vertical]Metrics();
  
  return (
    <VerticalDashboardLayout ...>
       {/* Implementation */}
    </VerticalDashboardLayout>
  );
}
```

## 4. Update Vertical Landing Page

Edit `frontend/src/app/verticals/[vertical-name]/page.tsx` to add a link to the new dashboard.
- Add a "Launch Portal" or "Dashboard" button in the Hero section.
- Ensure efficient navigation.

## 5. Verify Types

Ensure strict type compliance:
- `SystemHealth` must have `status: 'HEALTHY' | ...`
- `Alert` severity must be typed (use explicit type in `api.ts`).
- `QuickAction` variants should be `default`, `outline`, or `secondary`.
