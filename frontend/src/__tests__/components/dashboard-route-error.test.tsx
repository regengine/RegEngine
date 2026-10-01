import { fireEvent, render, screen } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import DashboardError from '@/app/dashboard/error';
import ReceivingError from '@/app/dashboard/receiving/error';
import { captureError } from '@/instrumentation-client';
vi.mock('@/instrumentation-client',()=>({captureError:vi.fn()}));
describe('handled route errors',()=>{
 it.each([DashboardError,ReceivingError])('reports a safe category and retains retry', Component=>{
  vi.mocked(captureError).mockClear(); const reset=vi.fn();
  render(<Component error={new Error('Private credential details')} reset={reset}/>);
  expect(captureError).toHaveBeenCalledTimes(1);
  expect(vi.mocked(captureError).mock.calls[0][0].message).toBe('Dashboard route render failed');
  expect(screen.queryByText('Private credential details')).toBeNull();
  fireEvent.click(screen.getByRole('button',{name:'Try Again'})); expect(reset).toHaveBeenCalledTimes(1);
 });
});
