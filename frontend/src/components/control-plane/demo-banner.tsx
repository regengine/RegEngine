'use client';

import { Callout } from '@/components/ui/callout';

export function DemoBanner({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <Callout tone="warning" role="status">
      <span>
        <strong className="font-medium text-re-text-primary">Sample Data</strong> — Backend unavailable.
        Data will appear once services are connected.
      </span>
    </Callout>
  );
}
