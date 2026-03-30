'use client';

import { useState } from 'react';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from '@/components/ui/dialog';
import { Paintbrush } from 'lucide-react';

interface MassFillDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  headers: string[];
  onApply: (column: string, value: string, onlyEmpty: boolean) => void;
}

export function MassFillDialog({ open, onOpenChange, headers, onApply }: MassFillDialogProps) {
  const [selectedColumn, setSelectedColumn] = useState(headers[0] || '');
  const [fillValue, setFillValue] = useState('');
  const [onlyEmpty, setOnlyEmpty] = useState(true);

  function handleApply() {
    if (!selectedColumn || !fillValue.trim()) return;
    onApply(selectedColumn, fillValue.trim(), onlyEmpty);
    setFillValue('');
    onOpenChange(false);
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#1a1a2e] border-[var(--re-surface-border)] text-[var(--re-text-primary)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-[var(--re-text-primary)]">
            <Paintbrush className="w-4 h-4 text-[var(--re-brand)]" />
            Mass Fill Column
          </DialogTitle>
          <DialogDescription className="text-[var(--re-text-muted)]">
            Fill multiple cells at once to fix repeated errors quickly.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Column selector */}
          <div className="space-y-1.5">
            <label className="text-[0.7rem] font-medium text-[var(--re-text-secondary)]">Column</label>
            <select
              value={selectedColumn}
              onChange={(e) => setSelectedColumn(e.target.value)}
              className="w-full bg-[var(--re-surface-base)] border border-[var(--re-surface-border)] rounded-lg px-3 py-2 text-[0.75rem] text-[var(--re-text-primary)] focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)]/30"
            >
              {headers.map((h) => (
                <option key={h} value={h}>{h}</option>
              ))}
            </select>
          </div>

          {/* Fill value */}
          <div className="space-y-1.5">
            <label className="text-[0.7rem] font-medium text-[var(--re-text-secondary)]">Fill value</label>
            <input
              type="text"
              value={fillValue}
              onChange={(e) => setFillValue(e.target.value)}
              placeholder="e.g., lbs"
              className="w-full bg-[var(--re-surface-base)] border border-[var(--re-surface-border)] rounded-lg px-3 py-2 text-[0.75rem] font-mono text-[var(--re-text-primary)] placeholder:text-[var(--re-text-disabled)] focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)]/30"
              onKeyDown={(e) => { if (e.key === 'Enter') handleApply(); }}
            />
          </div>

          {/* Only empty checkbox */}
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={onlyEmpty}
              onChange={(e) => setOnlyEmpty(e.target.checked)}
              className="rounded border-[var(--re-surface-border)] bg-[var(--re-surface-base)]"
            />
            <span className="text-[0.7rem] text-[var(--re-text-secondary)]">
              Only fill empty cells
            </span>
          </label>
        </div>

        <DialogFooter>
          <button
            onClick={() => onOpenChange(false)}
            className="px-4 py-2 text-[0.75rem] text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleApply}
            disabled={!fillValue.trim()}
            className="px-4 py-2 bg-[var(--re-brand)] text-white rounded-lg text-[0.75rem] font-semibold hover:bg-[var(--re-brand-dark)] disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            Apply to {onlyEmpty ? 'empty cells' : 'all cells'}
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
