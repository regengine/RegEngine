'use client';

import { Calendar, ArrowRight, Shield, Lock, Zap, GitBranch } from 'lucide-react';

const CALENDLY_LINK = 'https://calendly.com/regengine/fsma-strategy-session';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

interface SandboxResultsCTAProps {
  mode: 'failures' | 'all_clear' | 'trace_complete';
  /** Number of non-compliant events or total defects */
  defectCount?: number;
  /** Total events evaluated */
  eventCount?: number;
  /** For trace mode */
  lotCount?: number;
  facilityCount?: number;
  /** PostHog capture function */
  onTrack?: (event: string, metadata?: Record<string, unknown>) => void;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function SandboxResultsCTA({
  mode,
  defectCount = 0,
  eventCount = 0,
  lotCount = 0,
  facilityCount = 0,
  onTrack,
}: SandboxResultsCTAProps) {
  function openCalendly(ctaType: string) {
    onTrack?.('SANDBOX_CTA_CLICK', {
      cta_type: ctaType,
      mode,
      defect_count: defectCount,
      event_count: eventCount,
      lot_count: lotCount,
      facility_count: facilityCount,
    });
    // Pass context into Calendly URL so Chris knows the caller's compliance state
    const params = new URLSearchParams({
      a1: mode,                          // "failures" | "all_clear" | "trace_complete"
      a2: String(defectCount),           // defect count
      a3: String(eventCount),            // event count
    });
    window.open(`${CALENDLY_LINK}?${params.toString()}`, '_blank');
  }

  function handleSecondary(ctaType: string, href: string) {
    onTrack?.('SANDBOX_CTA_CLICK', {
      cta_type: ctaType,
      mode,
      defect_count: defectCount,
    });
    window.open(href, '_blank');
  }

  // ── Mode A: Failures ──
  if (mode === 'failures') {
    return (
      <div className="rounded-lg border border-[var(--re-brand)]/30 bg-[var(--re-brand)]/5 p-4">
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-lg bg-[var(--re-brand)]/10 flex-shrink-0">
            <Zap className="w-5 h-5 text-[var(--re-brand)]" />
          </div>
          <div className="flex-1 min-w-0">
            <h4 className="text-[0.8rem] font-semibold text-[var(--re-text-primary)]">
              You have {defectCount} compliance gap{defectCount !== 1 ? 's' : ''}. We can close them automatically.
            </h4>
            <p className="text-[0.7rem] text-[var(--re-text-secondary)] mt-1">
              RegEngine connects to your ERP and validates every shipment in real-time — no more manual CSV fixes.
            </p>
            <div className="flex flex-wrap items-center gap-2 mt-3">
              <button
                onClick={() => openCalendly('book_call')}
                className="inline-flex items-center gap-1.5 bg-[var(--re-brand)] text-white px-4 py-2 rounded-lg text-[0.7rem] font-semibold transition-all hover:bg-[var(--re-brand-dark)] cursor-pointer"
              >
                <Calendar className="w-3.5 h-3.5" />
                Book a 15-Min Strategy Call
              </button>
              <button
                onClick={() => handleSecondary('pricing', '/pricing')}
                className="inline-flex items-center gap-1 text-[0.7rem] text-[var(--re-brand)] hover:underline cursor-pointer"
              >
                See Pricing <ArrowRight className="w-3 h-3" />
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Mode B: All Clear ──
  if (mode === 'all_clear') {
    return (
      <div className="rounded-lg border border-emerald-500/30 bg-emerald-500/5 p-4">
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-lg bg-emerald-500/10 flex-shrink-0">
            <Shield className="w-5 h-5 text-emerald-400" />
          </div>
          <div className="flex-1 min-w-0">
            <h4 className="text-[0.8rem] font-semibold text-emerald-300">
              Your data is 100% compliant. Now automate it.
            </h4>
            <p className="text-[0.7rem] text-[var(--re-text-secondary)] mt-1">
              You just fixed {eventCount} event{eventCount !== 1 ? 's' : ''} by hand. RegEngine does this for every shipment, automatically.
            </p>
            <div className="flex flex-wrap items-center gap-2 mt-3">
              <button
                onClick={() => openCalendly('automate')}
                className="inline-flex items-center gap-1.5 bg-emerald-500 text-white px-4 py-2 rounded-lg text-[0.7rem] font-semibold transition-all hover:bg-emerald-600 cursor-pointer"
              >
                <Zap className="w-3.5 h-3.5" />
                Automate My Compliance
              </button>
              <button
                onClick={() => handleSecondary('founding_cohort', '/pricing')}
                className="inline-flex items-center gap-1 text-[0.7rem] text-emerald-400 hover:underline cursor-pointer"
              >
                Join Founding Cohort — 50% Off for Life <ArrowRight className="w-3 h-3" />
              </button>
            </div>
            <div className="flex items-center gap-4 mt-3 pt-3 border-t border-emerald-500/15">
              {[
                { icon: Lock, label: 'No data stored' },
                { icon: Shield, label: 'SOC 2 Type II' },
                { icon: Shield, label: 'FDA 204 Compliant' },
              ].map(({ icon: Icon, label }) => (
                <span key={label} className="flex items-center gap-1 text-[0.6rem] text-[var(--re-text-disabled)]">
                  <Icon className="w-3 h-3" /> {label}
                </span>
              ))}
            </div>
          </div>
        </div>
      </div>
    );
  }

  // ── Mode C: Trace Complete ──
  if (mode === 'trace_complete') {
    return (
      <div className="rounded-lg border border-purple-500/30 bg-purple-500/5 p-4">
        <div className="flex items-start gap-3">
          <div className="p-2 rounded-lg bg-purple-500/10 flex-shrink-0">
            <GitBranch className="w-5 h-5 text-purple-400" />
          </div>
          <div className="flex-1 min-w-0">
            <h4 className="text-[0.8rem] font-semibold text-purple-300">
              This trace covered {lotCount} lot{lotCount !== 1 ? 's' : ''} across {facilityCount} facilit{facilityCount !== 1 ? 'ies' : 'y'}. Imagine doing this during a recall.
            </h4>
            <p className="text-[0.7rem] text-[var(--re-text-secondary)] mt-1">
              RegEngine maintains a live genealogy graph of your entire supply chain. One-click FDA 204(d) response in under 24 hours.
            </p>
            <div className="flex flex-wrap items-center gap-2 mt-3">
              <button
                onClick={() => handleSecondary('recall_walkthrough', '/walkthrough')}
                className="inline-flex items-center gap-1.5 bg-purple-500 text-white px-4 py-2 rounded-lg text-[0.7rem] font-semibold transition-all hover:bg-purple-600 cursor-pointer"
              >
                See How Recall Works <ArrowRight className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => openCalendly('book_call_trace')}
                className="inline-flex items-center gap-1 text-[0.7rem] text-purple-400 hover:underline cursor-pointer"
              >
                <Calendar className="w-3 h-3" /> Book a Call
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  return null;
}
