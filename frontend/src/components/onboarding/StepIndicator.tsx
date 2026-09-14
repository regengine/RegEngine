/**
 * StepIndicator — the "Step X of N" marker used across onboarding pages.
 *
 * SPEC §6 / proposal-A §6.6: a neutral mono Badge at the top of the step card,
 * so the card says where you are independently of the layout's stepper. The
 * rendered text stays "Step 1 of 3" (uppercased visually only) and the
 * aria-label is unchanged — both are asserted by page tests.
 */
import { Badge } from "@/components/ui/badge";

interface StepIndicatorProps {
    /** Current step number (1-based). */
    step: number;
    /** Total number of steps. Defaults to 3. */
    total?: number;
}

export function StepIndicator({ step, total = 3 }: StepIndicatorProps) {
    return (
        <Badge
            tone="neutral"
            size="sm"
            mono
            aria-label={`Step ${step} of ${total}`}
            className="uppercase"
        >
            Step {step} of {total}
        </Badge>
    );
}
