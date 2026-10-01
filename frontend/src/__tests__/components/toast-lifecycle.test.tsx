import { act, render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { toast, useToast } from '@/components/ui/use-toast';
import { Toaster } from '@/components/ui/toaster';
function State() { const { toasts } = useToast(); return <output data-testid="state">{JSON.stringify(toasts)}</output>; }
describe('toast lifecycle', () => {
 it('preserves the handle identity for update, close and dismissal', () => {
  render(<><State/><Toaster/></>);
  let handle!: ReturnType<typeof toast>;
  act(() => { handle = toast({title:'Receiving Session Started'}); });
  expect(JSON.parse(screen.getByTestId('state').textContent || '[]')[0]?.id).toBe(handle.id);
  act(() => handle.update({title:'Receiving complete'}));
  expect(screen.getByText('Receiving complete')).toBeInTheDocument();
  expect(screen.getByRole('button', {name:'Close notification'})).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', {name:'Close notification'}));
  expect(JSON.parse(screen.getByTestId('state').textContent || '[]')[0].open).toBe(false);
  act(() => { handle = toast({title:'Another notification'}); });
  act(() => handle.dismiss());
  expect(JSON.parse(screen.getByTestId('state').textContent || '[]')[0].open).toBe(false);
 });
 it('removes dismissed notifications after the bounded exit delay', () => {
  vi.useFakeTimers();
  render(<State/>);
  let handle!: ReturnType<typeof toast>;
  act(()=>{handle=toast({title:'Expires'}); handle.dismiss();});
  act(()=>vi.advanceTimersByTime(1000));
  expect(JSON.parse(screen.getByTestId('state').textContent || '[]')).toEqual([]);
  vi.useRealTimers();
 });
});
