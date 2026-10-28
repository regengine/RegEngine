import { Callout } from '@/components/ui/callout';
import { BETA_UNAVAILABLE_COPY } from '@/lib/dashboard-load-failure';

export interface BetaUnavailableStateProps {
    feature?: string;
}

export function BetaUnavailableState({ feature = 'This feature' }: BetaUnavailableStateProps) {
    return (
        <Callout tone="info" role="status" title={`${feature} is ${BETA_UNAVAILABLE_COPY}`}>
            <a href="/settings/support" className="text-small underline">Contact support</a>
        </Callout>
    );
}
