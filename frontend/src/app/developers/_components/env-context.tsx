'use client';

import { createContext, useContext, useState, type ReactNode } from 'react';

type Env = 'production' | 'sandbox';

const EnvContext = createContext<{
    env: Env;
    setEnv: (env: Env) => void;
    baseUrl: string;
    apiKey: string;
}>({
    env: 'production',
    setEnv: () => {},
    baseUrl: 'https://api.regengine.co',
    apiKey: 'rge_live_abc123',
});

export function EnvProvider({ children }: { children: ReactNode }) {
    const [env, setEnv] = useState<Env>('production');
    const baseUrl = env === 'production'
        ? 'https://api.regengine.co'
        : 'https://sandbox.regengine.co';
    const apiKey = env === 'production'
        ? 'rge_live_abc123'
        : 'rge_test_sandbox_key';
    return (
        <EnvContext.Provider value={{ env, setEnv, baseUrl, apiKey }}>
            {children}
        </EnvContext.Provider>
    );
}

export function useEnv() {
    return useContext(EnvContext);
}
