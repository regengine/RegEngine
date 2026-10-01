import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { expect, it, vi } from 'vitest';
import { useSystemMetrics } from '@/hooks/use-api';
const getMetrics = vi.hoisted(() => vi.fn());
vi.mock('@/lib/api-client', () => ({apiClient:{getSystemMetrics:()=>getMetrics()}}));
function wrapper({children}:{children:React.ReactNode}) {
 return <QueryClientProvider client={new QueryClient({defaultOptions:{queries:{retry:false}}})}>{children}</QueryClientProvider>;
}
it('keeps failed metrics unavailable instead of returning successful zero data', async()=>{
 getMetrics.mockRejectedValue(new Error('unavailable'));
 const {result} = renderHook(()=>useSystemMetrics(), {wrapper});
 await waitFor(()=>expect(result.current.isError).toBe(true));
 expect(result.current.data).toBeUndefined();
});
it('retains a successful zero result',async()=>{
 getMetrics.mockResolvedValue({compliance_score:0,events_ingested:0,open_alerts:0,chain_valid:false});
 const {result}=renderHook(()=>useSystemMetrics(),{wrapper});
 await waitFor(()=>expect(result.current.isSuccess).toBe(true));
 expect(result.current.data?.compliance_score).toBe(0);
});
