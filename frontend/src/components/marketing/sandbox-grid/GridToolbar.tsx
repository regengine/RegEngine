'use client';

import {
  Undo2, Redo2, Paintbrush, Download, ShieldCheck, ShieldAlert,
  ArrowLeft, Loader2, GitBranch, Clock, FileText,
} from 'lucide-react';

interface GridToolbarProps {
  criticalDefects: number;
  totalDefects: number;
  canUndo: boolean;
  canRedo: boolean;
  isEvaluating: boolean;
  rateLimitMsg?: string | null;
  showTrace: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onMassFill: () => void;
  onExportCsv: () => void;
  onPdfReport?: () => void;
  onBack: () => void;
  onToggleTrace: () => void;
}

export function GridToolbar({
  criticalDefects,
  totalDefects,
  canUndo,
  canRedo,
  isEvaluating,
  rateLimitMsg,
  showTrace,
  onUndo,
  onRedo,
  onMassFill,
  onExportCsv,
  onPdfReport,
  onBack,
  onToggleTrace,
}: GridToolbarProps) {
  const allClear = criticalDefects === 0 && totalDefects === 0;

  return (
    <div className="flex items-center justify-between gap-3 px-4 py-2.5 bg-[var(--re-surface-elevated)] border-b border-[var(--re-surface-border)]">
      {/* Left: back + defect counter */}
      <div className="flex items-center gap-3">
        <button
          onClick={onBack}
          className="flex items-center gap-1 text-[0.7rem] text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] transition-colors"
          title="Back to summary"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          Summary
        </button>

        <div className="w-px h-5 bg-[var(--re-surface-border)]" />

        {/* Defect counter */}
        <div className="flex items-center gap-2">
          {allClear ? (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-re-brand/15">
              <ShieldCheck className="w-3.5 h-3.5 text-re-brand" />
              <span className="text-[0.7rem] font-bold text-re-brand">All Clear</span>
            </div>
          ) : (
            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-re-danger-muted0/15">
              <ShieldAlert className="w-3.5 h-3.5 text-re-danger" />
              <span className="text-[0.7rem] font-bold text-re-danger">
                {criticalDefects} critical
              </span>
              {totalDefects > criticalDefects && (
                <span className="text-[0.6rem] text-re-warning">
                  + {totalDefects - criticalDefects} warning{totalDefects - criticalDefects !== 1 ? 's' : ''}
                </span>
              )}
            </div>
          )}

          {isEvaluating && (
            <Loader2 className="w-3.5 h-3.5 text-[var(--re-brand)] animate-spin" />
          )}

          {rateLimitMsg && (
            <div className="flex items-center gap-1 text-[0.6rem] text-amber-400">
              <Clock className="w-3 h-3" />
              {rateLimitMsg}
            </div>
          )}
        </div>
      </div>

      {/* Right: actions */}
      <div className="flex items-center gap-1.5">
        <button
          onClick={onUndo}
          disabled={!canUndo}
          className="p-1.5 rounded-md text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] hover:bg-[var(--re-surface-base)] disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          title="Undo (Ctrl+Z)"
        >
          <Undo2 className="w-3.5 h-3.5" />
        </button>
        <button
          onClick={onRedo}
          disabled={!canRedo}
          className="p-1.5 rounded-md text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] hover:bg-[var(--re-surface-base)] disabled:opacity-30 disabled:cursor-not-allowed transition-all"
          title="Redo (Ctrl+Shift+Z)"
        >
          <Redo2 className="w-3.5 h-3.5" />
        </button>

        <div className="w-px h-5 bg-[var(--re-surface-border)]" />

        <button
          onClick={onMassFill}
          className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[0.65rem] font-medium text-[var(--re-text-secondary)] hover:text-[var(--re-text-primary)] hover:bg-[var(--re-surface-base)] transition-all"
          title="Fill empty cells in bulk"
        >
          <Paintbrush className="w-3.5 h-3.5" />
          Mass Fill
        </button>

        <button
          onClick={onToggleTrace}
          className={`flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[0.65rem] font-medium transition-all ${
            showTrace
              ? 'bg-[var(--re-brand)]/15 text-[var(--re-brand)] border border-[var(--re-brand)]/30'
              : 'text-[var(--re-text-secondary)] hover:text-[var(--re-text-primary)] hover:bg-[var(--re-surface-base)]'
          }`}
          title="Trace lot codes through the supply chain"
        >
          <GitBranch className="w-3.5 h-3.5" />
          Trace
        </button>

        {onPdfReport && (
          <button
            onClick={onPdfReport}
            className="flex items-center gap-1.5 px-2.5 py-1.5 rounded-md text-[0.65rem] font-medium text-[var(--re-text-secondary)] hover:text-[var(--re-text-primary)] hover:bg-[var(--re-surface-base)] transition-all"
            title="Download branded PDF compliance report"
          >
            <FileText className="w-3.5 h-3.5" />
            PDF Report
          </button>
        )}

        <button
          onClick={onExportCsv}
          disabled={criticalDefects > 0}
          className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-[0.65rem] font-semibold transition-all ${
            criticalDefects === 0
              ? 'bg-re-brand text-white hover:bg-re-brand'
              : 'bg-[var(--re-surface-base)] text-[var(--re-text-disabled)] cursor-not-allowed'
          }`}
          title={criticalDefects > 0 ? 'Fix all critical defects to enable export' : 'Download corrected CSV'}
        >
          <Download className="w-3.5 h-3.5" />
          Export CSV
        </button>
      </div>
    </div>
  );
}
