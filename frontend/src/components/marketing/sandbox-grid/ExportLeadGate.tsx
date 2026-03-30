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
import { Download, Mail, ArrowRight, Lock } from 'lucide-react';
import { isValidEmail } from '@/lib/validation';

interface ExportLeadGateProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** Fires when user submits email or skips — parent should proceed with export */
  onExport: () => void;
  /** PostHog tracking */
  onTrack?: (event: string, metadata?: Record<string, unknown>) => void;
  defectCount?: number;
  eventCount?: number;
}

export function ExportLeadGate({
  open,
  onOpenChange,
  onExport,
  onTrack,
  defectCount = 0,
  eventCount = 0,
}: ExportLeadGateProps) {
  const [email, setEmail] = useState('');

  function handleSubmit() {
    if (!isValidEmail(email)) return;
    onTrack?.('SANDBOX_LEAD_CAPTURE', {
      email: email.trim(),
      defect_count: defectCount,
      event_count: eventCount,
    });
    onOpenChange(false);
    onExport();
    setEmail('');
  }

  function handleSkip() {
    onTrack?.('SANDBOX_LEAD_SKIP', {
      defect_count: defectCount,
      event_count: eventCount,
    });
    onOpenChange(false);
    onExport();
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="bg-[#1a1a2e] border-[var(--re-surface-border)] text-[var(--re-text-primary)] sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-[var(--re-text-primary)]">
            <Download className="w-4 h-4 text-[var(--re-brand)]" />
            Export Your Results
          </DialogTitle>
          <DialogDescription className="text-[var(--re-text-muted)]">
            Get your corrected data plus a personalized compliance action plan.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Value prop */}
          <div className="rounded-lg border border-[var(--re-brand)]/20 bg-[var(--re-brand)]/5 p-3">
            <div className="flex items-center gap-2 mb-2">
              <Mail className="w-4 h-4 text-[var(--re-brand)]" />
              <span className="text-[0.7rem] font-semibold text-[var(--re-text-primary)]">
                Enter your email to receive:
              </span>
            </div>
            <ul className="space-y-1 ml-6">
              <li className="text-[0.65rem] text-[var(--re-text-secondary)] list-disc">
                Your corrected CSV file
              </li>
              <li className="text-[0.65rem] text-[var(--re-text-secondary)] list-disc">
                A personalized action plan to close remaining gaps
              </li>
              <li className="text-[0.65rem] text-[var(--re-text-secondary)] list-disc">
                FSMA 204 compliance tips from our CEO
              </li>
            </ul>
          </div>

          {/* Email input */}
          <div className="space-y-1.5">
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@company.com"
              className="w-full bg-[var(--re-surface-base)] border border-[var(--re-surface-border)] rounded-lg px-3 py-2.5 text-[0.75rem] text-[var(--re-text-primary)] placeholder:text-[var(--re-text-disabled)] focus:outline-none focus:ring-2 focus:ring-[var(--re-brand)]/30"
              onKeyDown={(e) => {
                if (e.key === 'Enter' && isValidEmail(email)) handleSubmit();
              }}
            />
          </div>

          {/* Trust badge */}
          <div className="flex items-center gap-1.5 text-[0.6rem] text-[var(--re-text-disabled)]">
            <Lock className="w-3 h-3" />
            No spam. No data stored. Just a one-time follow-up.
          </div>
        </div>

        <DialogFooter className="flex flex-col gap-2 sm:flex-col">
          <button
            onClick={handleSubmit}
            disabled={!isValidEmail(email)}
            className="w-full px-4 py-2.5 bg-[var(--re-brand)] text-white rounded-lg text-[0.75rem] font-semibold hover:bg-[var(--re-brand-dark)] disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center gap-1.5"
          >
            Send My Report <ArrowRight className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleSkip}
            className="w-full px-4 py-2 text-[0.7rem] text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)] transition-colors"
          >
            Skip, just download
          </button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
