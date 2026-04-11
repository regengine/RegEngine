'use client';

import { AlertTriangle } from 'lucide-react';

export function DemoBanner({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <div className="flex items-center gap-2 p-3 rounded-xl bg-re-warning-muted0/[0.08] border border-re-warning/20 text-re-warning dark:text-re-warning text-xs">
      <AlertTriangle className="h-3.5 w-3.5 flex-shrink-0" />
      <span>
        <strong>Sample Data</strong> — Backend unavailable.
        Data will appear once services are connected.
      </span>
    </div>
  );
}
