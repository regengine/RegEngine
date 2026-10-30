'use client';

import { HueDot } from '@/components/demo-workspace/HueDot';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card } from '@/components/ui/card';
import { downloadText } from '@/lib/demo-workspace/download';
import { buildManifest, type Package } from '@/lib/demo-workspace/model';
import { cn } from '@/lib/utils';

export function ExportView({ packages }: { packages: Package[] }) {
  return (
    <>
      <div className="grid grid-cols-[repeat(auto-fit,minmax(300px,1fr))] gap-4">
        {packages.map((pkg) => (
          <Card key={pkg.scenarioId} className={cn('overflow-hidden', pkg.ready && 'border-re-brand')}>
            <div className="flex items-center justify-between gap-2.5 border-b border-re-border-subtle bg-re-surface-elevated px-4 py-2.5">
              <span className="inline-flex items-center gap-2 text-ui font-semibold text-re-text-primary">
                <HueDot hue={pkg.hue} />
                {pkg.food}
              </span>
              <Badge tone={pkg.ready ? 'success' : 'warning'} size="sm" mono>
                {pkg.badge}
              </Badge>
            </div>
            <div className="px-4 py-3.5 text-small leading-relaxed text-re-text-tertiary">
              <p className="font-mono text-re-text-primary">{pkg.file}</p>
              <p>{pkg.line}</p>
              <p className="truncate font-mono text-re-text-muted">manifest {pkg.manifest}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button
                  type="button"
                  variant="primary"
                  size="sm"
                  onClick={() => downloadText(pkg.file, pkg.csv, 'text/csv')}
                >
                  Download CSV
                </Button>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() =>
                    downloadText(`manifest_${pkg.scenarioId}.txt`, buildManifest(pkg.file, pkg.manifest), 'text/plain')
                  }
                >
                  Manifest
                </Button>
              </div>
            </div>
          </Card>
        ))}
      </div>
      <p className="mt-5 max-w-[760px] text-small leading-relaxed text-re-text-muted">
        Packages are FDA-shaped sortable spreadsheets built from the committed records of each chain. Open records are
        listed in a separate sheet, never silently dropped. The manifest lists every file with its SHA-256; check it on
        your own machine with <span className="font-mono">verify_chain.py</span>. A package is a record of what you
        hold, not a certification and not a statement that any request has been met.
      </p>
    </>
  );
}
