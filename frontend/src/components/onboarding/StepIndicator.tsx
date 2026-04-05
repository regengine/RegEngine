/**
 * StepIndicator — lightweight "Step X of N" pill used across onboarding pages.
 *
 * Placed inside each page's CardHeader so users always know where they are
 * in the setup flow independent of the layout's visual stepper.
 */

interface StepIndicatorProps {
    /** Current step number (1-based). */
    step: number;
    /** Total number of steps. Defaults to 3. */
    total?: number;
}

export function StepIndicator({ step, total = 3 }: StepIndicatorProps) {
    return (
        <span
            aria-label={`Step ${step} of ${total}`}
            className="inline-flex items-center rounded-full border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] px-2.5 py-0.5 text-[11px] font-medium tracking-wide text-[var(--re-text-muted)]"
        >
            Step {step} of {total}
        </span>
    );
}
