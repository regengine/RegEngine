import React from 'react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor, cleanup } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AuthProvider, useAuth } from '@/lib/auth-context';

vi.mock('@/lib/api-client', () => ({ apiClient: {
  getSystemMetrics: vi.fn(), setAccessToken: vi.fn(), setUser: vi.fn(), setCurrentTenant: vi.fn(),
} }));

beforeEach(() => {
  cleanup();
  vi.clearAllMocks();
  localStorage.clear();
});

describe('session boundary reliability', () => {
  it('stalled session hydration settles without manufacturing authentication', async () => {
    vi.useFakeTimers();
    vi.stubGlobal('fetch', vi.fn(() => new Promise(() => {})));
    const wrapper = ({children}: {children:React.ReactNode}) => <AuthProvider>{children}</AuthProvider>;
    const hook = renderHook(useAuth,{wrapper});
    try {
      await act(async () => {await vi.advanceTimersByTimeAsync(10_001);});
      expect(hook.result.current.isHydrated).toBe(true);
      expect(hook.result.current.isAuthenticated).toBe(false);
    } finally {hook.unmount(); vi.useRealTimers();vi.unstubAllGlobals();}
  });

  it('finishes hydration when browser storage is unavailable', async () => {
    vi.spyOn(Storage.prototype, 'getItem').mockImplementation(() => {throw new DOMException('denied', 'SecurityError');});
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true,json:async () => ({authenticated:false})}));
    const wrapper = ({children}: {children:React.ReactNode}) => <AuthProvider>{children}</AuthProvider>;
    const hook = renderHook(useAuth,{wrapper});
    await waitFor(() => expect(hook.result.current.isHydrated).toBe(true));
    expect(hook.result.current.isAuthenticated).toBe(false);
    hook.unmount(); vi.restoreAllMocks(); vi.unstubAllGlobals();
  });

  it('prevents a cancelled old request from repopulating sensitive cache after logout', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ok:true,json:async () => ({authenticated:false})}));
    const client = new QueryClient();
    let resolve!: (value:string) => void;
    const pending = new Promise<string>(r => {resolve=r;});
    const oldRequest = client.fetchQuery({queryKey:['sensitive'],queryFn:() => pending}).catch(() => undefined);
    const wrapper = ({children}: {children:React.ReactNode}) => <QueryClientProvider client={client}><AuthProvider resetSessionCache={() => {void client.cancelQueries();client.clear();}}>{children}</AuthProvider></QueryClientProvider>;
    const hook = renderHook(useAuth,{wrapper});
    await waitFor(() => expect(hook.result.current.isHydrated).toBe(true));
    await act(async () => {await hook.result.current.logout(); resolve('account-a'); await oldRequest;});
    expect(client.getQueryData(['sensitive'])).toBeUndefined();
    hook.unmount(); vi.unstubAllGlobals();
  });

  it.each([403, 503, 'offline'] as const)('rejects unconfirmed logout (%s)', async (status) => {
    const fetchMock = vi.fn(async (_url: string, options?: RequestInit) => {
      if (options?.method === 'DELETE') { if (status === 'offline') throw new Error('offline'); return { ok: false, status }; }
      if (options?.method === 'POST') return { ok: true, status: 200 };
      return { ok: true, json: async () => ({ authenticated: false, has_api_key: false, has_credentials: false, tenant_id: null, user: null }) };
    });
    vi.stubGlobal('fetch', fetchMock);
    const wrapper = ({ children }: {children: React.ReactNode}) => <AuthProvider>{children}</AuthProvider>;
    const hook = renderHook(() => useAuth(), { wrapper });
    await waitFor(() => expect(hook.result.current.isHydrated).toBe(true));
    await act(async () => {
      await hook.result.current.login('synthetic-diagnostic-token', { id: 'synthetic-user', email: 'audit@example.invalid', permissions: [] } as any, 'synthetic-tenant');
    });
    expect(hook.result.current.isAuthenticated).toBe(true);
    await act(async () => { await expect(hook.result.current.logout()).rejects.toThrow(/confirm/i); });
    expect(fetchMock.mock.calls.some(([, options]) => options?.method === 'DELETE')).toBe(true);
    expect(hook.result.current.isAuthenticated).toBe(false);
    hook.unmount();
    vi.unstubAllGlobals();
  });
});
