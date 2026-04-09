'use client';

import { AlertTriangle, LogIn } from 'lucide-react';

export function DemoBanner({ visible, reason }: { visible: boolean; reason?: 'auth' | 'unreachable' }) {
  if (!visible) return null;

  const isAuth = reason === 'auth';
  const Icon = isAuth ? LogIn : AlertTriangle;

  return (
    <div className="flex items-center gap-2 p-3 rounded-xl bg-amber-500/[0.08] border border-amber-500/20 text-amber-600 dark:text-amber-400 text-xs">
      <Icon className="h-3.5 w-3.5 flex-shrink-0" />
      <span>
        {isAuth ? (
          <><strong>Sample Data</strong> — Log in to see live data.</>
        ) : (
          <><strong>Sample Data</strong> — Backend unavailable. Showing demo data.
          Import real data via Dashboard → Data Import to see live results.</>
        )}
      </span>
    </div>
  );
}
