'use client';

import { useState } from 'react';
import { ShieldAlert, AlertTriangle, ExternalLink, Lightbulb, Plus, Pencil, Paintbrush } from 'lucide-react';
import type { CellError, ResolutionOption } from './types';
import { getResolutionOptions } from './resolution-recipes';

interface FixItTooltipProps {
  errors: CellError[];
  rowIndex: number;
  children: React.ReactNode;
  /** Callbacks for resolution actions */
  onAddRow?: (cteType: string, prefill: Record<string, string>) => void;
  onEditCell?: (row: number, column: string) => void;
  onMassFill?: (column: string, value: string) => void;
}

const ACTION_ICONS = {
  add_row: Plus,
  edit_cell: Pencil,
  mass_fill: Paintbrush,
} as const;

export function FixItTooltip({ errors, rowIndex, children, onAddRow, onEditCell, onMassFill }: FixItTooltipProps) {
  const [isVisible, setIsVisible] = useState(false);

  if (errors.length === 0) return <>{children}</>;

  const hasCritical = errors.some((e) => e.severity === 'critical');

  // Gather resolution options for all errors
  const allRecipes: { error: CellError; options: ResolutionOption[] }[] = errors
    .filter((e) => e.evidence || e.isKdeError)
    .map((e) => ({ error: e, options: getResolutionOptions(e, rowIndex) }))
    .filter((r) => r.options.length > 0);

  function handleOptionClick(option: ResolutionOption) {
    setIsVisible(false);
    switch (option.action) {
      case 'add_row':
        onAddRow?.(option.cteType || '', option.prefill || {});
        break;
      case 'edit_cell':
        onEditCell?.(option.targetRow ?? rowIndex, option.targetColumn || '');
        break;
      case 'mass_fill':
        onMassFill?.(option.fillColumn || '', option.fillValue || '');
        break;
    }
  }

  return (
    <div
      className="relative"
      onMouseEnter={() => setIsVisible(true)}
      onMouseLeave={() => setIsVisible(false)}
    >
      {children}
      {isVisible && (
        <div
          className="absolute z-50 bottom-full left-0 mb-2 w-80 bg-[#1a1a2e] border border-[var(--re-surface-border)] rounded-lg shadow-2xl p-0 overflow-hidden"
          role="tooltip"
        >
          {/* Header */}
          <div className={`px-3 py-2 flex items-center gap-2 ${hasCritical ? 'bg-re-danger-muted0/15' : 'bg-re-warning-muted0/15'}`}>
            {hasCritical
              ? <ShieldAlert className="w-3.5 h-3.5 text-re-danger" />
              : <AlertTriangle className="w-3.5 h-3.5 text-re-warning" />}
            <span className={`text-[0.7rem] font-semibold ${hasCritical ? 'text-re-danger' : 'text-re-warning'}`}>
              {errors.length} issue{errors.length !== 1 ? 's' : ''} found
            </span>
          </div>

          {/* Error list */}
          <div className="p-3 space-y-3 max-h-72 overflow-y-auto">
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
                  <div className="text-[0.6rem] text-re-brand italic leading-relaxed">
                    Fix: {err.remediation}
                  </div>
                )}

                {i < errors.length - 1 && (
                  <div className="border-t border-[var(--re-surface-border)] mt-2" />
                )}
              </div>
            ))}
          </div>

          {/* Resolution Options */}
          {allRecipes.length > 0 && (
            <div className="border-t border-[var(--re-surface-border)] p-3 space-y-2">
              <div className="flex items-center gap-1.5 mb-1">
                <Lightbulb className="w-3 h-3 text-[var(--re-brand)]" />
                <span className="text-[0.6rem] font-semibold text-[var(--re-brand)]">
                  Guided Resolution
                </span>
              </div>

              {allRecipes.flatMap(({ options }) => options).map((option) => {
                const Icon = ACTION_ICONS[option.action];
                return (
                  <button
                    key={option.id}
                    onClick={() => handleOptionClick(option)}
                    className="w-full flex items-start gap-2 px-2 py-1.5 rounded-md text-left transition-colors hover:bg-[var(--re-surface-elevated)] group cursor-pointer"
                  >
                    <Icon className="w-3 h-3 mt-0.5 text-[var(--re-brand)] flex-shrink-0 group-hover:text-[var(--re-text-primary)]" />
                    <div>
                      <div className="text-[0.6rem] font-medium text-[var(--re-text-primary)]">
                        {option.label}
                      </div>
                      <div className="text-[0.55rem] text-[var(--re-text-muted)] leading-snug">
                        {option.description}
                      </div>
                    </div>
                  </button>
                );
              })}
            </div>
          )}

          {/* Arrow */}
          <div className="absolute top-full left-4 w-0 h-0 border-l-[6px] border-r-[6px] border-t-[6px] border-l-transparent border-r-transparent border-t-[#1a1a2e]" />
        </div>
      )}
    </div>
  );
}
