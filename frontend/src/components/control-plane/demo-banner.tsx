'use client';

import Link from 'next/link';
import { Callout } from '@/components/ui/callout';

export function DemoBanner({ visible }: { visible: boolean }) {
  if (!visible) return null;
  return (
    <Callout tone="warning" role="status">
      <span>
        <strong className="font-medium text-re-text-primary">No data yet</strong>: nothing
        is connected for this view yet.{' '}
        <Link href="/ingest" className="underline hover:no-underline">
          Connect real data on the Ingest page
        </Link>
      </span>
    </Callout>
  );
}
