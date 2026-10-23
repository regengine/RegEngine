import { useEffect, useState } from 'react';

export type LoadingPhase = 'loading' | 'slow' | 'timeout';

/** After this long a skeleton tells the user it is still working. */
export const SLOW_LOADING_MS = 5_000;
/** After this long a skeleton gives up and offers a retry. */
export const LOADING_TIMEOUT_MS = 20_000;

/**
 * Tracks how long a skeleton has been on screen. Resets whenever `active`
 * turns false, so a retry starts the clock again.
 */
export function useLoadingPhase(
  active: boolean,
  { slowMs = SLOW_LOADING_MS, timeoutMs = LOADING_TIMEOUT_MS }: { slowMs?: number; timeoutMs?: number } = {},
): LoadingPhase {
  const [phase, setPhase] = useState<LoadingPhase>('loading');

  useEffect(() => {
    if (!active) return;
    const slow = setTimeout(() => setPhase('slow'), slowMs);
    const timeout = setTimeout(() => setPhase('timeout'), timeoutMs);
    return () => {
      clearTimeout(slow);
      clearTimeout(timeout);
      setPhase('loading');
    };
  }, [active, slowMs, timeoutMs]);

  return active ? phase : 'loading';
}
