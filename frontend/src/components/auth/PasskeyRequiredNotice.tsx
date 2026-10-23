import type { ReactNode } from 'react';
import { Fingerprint } from 'lucide-react';

import { Callout } from '@/components/ui/callout';

/**
 * Shown when passkey step-up failed or is unavailable: the protected action
 * did not run and still needs a passkey-backed session.
 */
export function PasskeyRequiredNotice({ children }: { children: ReactNode }) {
  return (
    <Callout tone="danger" role="alert" icon={Fingerprint} title="Passkey required">
      {children}
    </Callout>
  );
}
