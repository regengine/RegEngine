'use client';

import type { ReactNode } from 'react';
import { EnvProvider } from './env-context';

export function DevProviders({ children }: { children: ReactNode }) {
    return <EnvProvider>{children}</EnvProvider>;
}
