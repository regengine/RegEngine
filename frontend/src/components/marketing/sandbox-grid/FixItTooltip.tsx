'use client';

import { useState } from 'react';
import { ShieldAlert, AlertTriangle, ExternalLink } from 'lucide-react';
import type { CellError } from './types';

interface FixItTooltipProps {
  errors: CellError[];
  children: React.ReactNode;
}

export function FixItTooltip({ errors, children }: FixItTooltipProps) {
  const [isVisible, setIsVisible] = useState(false);

  if (errors.length === 0) return <>{children}</>;

  const hasCritical = errors.some((e) => e.severity === 'critical');

  return (
    <div
      className="relative"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {children}
      {isVisible && (
        <div
          className="absolute z-50 bottom-full left-0 mb-2 w-72 bg-[#1a1a2e] border border-[var(--re-surface-border)] rounded-lg shadow-2xl p-0 overflow-hidden"
          role="tooltip"
        >
          {/* Header */}
          <div className={`px-3 py-2 flex items-center gap-2 ${hasCritical ? 'bg-red-500/15' : 'bg-amber-500/15'}`}>
            {hasCritical
              ? <ShieldAlert className="w-3.5 h-3.5 text-red-400" />
              : <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />}
            <span className={`text-[0.7rem] font-semibold ${hasCritical ? 'text-red-400' : 'text-amber-400'}`}>
              {errors.length} issue{errors.length !== 1 ? 's' : ''} found
            </span>
          </div>

          {/* Error list */}
          <div className="p-3 space-y-3 max-h-64 overflow-y-auto">
            {errors.map((err, i) => (
              <div key={i} className="space-y-1">
                <div className="text-[0.65rem] font-semibold text-[var(--re-text-primary)]">
                  {err.ruleTitle}
                </div>

                {err.citation && (
                  <div className="flex items-center gap-1">
                    <span className="text-[0.6rem] text-indigo-400 font-mono">{err.citation}</span>
                    <ExternalLink className="w-2.5 h-2.5 text-indigo-400" />
                  </div>
                )}

                {err.whyFailed && (
                  <div className="text-[0.6rem] text-[var(--re-text-secondary)] leading-relaxed">
                    {err.whyFailed}
                  </div>
                )}

                {err.remediation && (
                  <div className="text-[0.6rem] text-emerald-400 italic leading-relaxed">
                    Fix: {err.remediation}
                  </div>
                )}

                {i < errors.length - 1 && (
                  <div className="border-t border-[var(--re-surface-border)] mt-2" />
                )}
              </div>
            ))}
          </div>

          {/* Arrow */}
          <div className="absolute top-full left-4 w-0 h-0 border-l-[6px] border-r-[6px] border-t-[6px] border-l-transparent border-r-transparent border-t-[#1a1a2e]" />
        </div>
      )}
    </div>
  );
}
