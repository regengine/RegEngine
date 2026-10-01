import { act, fireEvent, render, screen, within, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import DashboardLayout from '@/app/dashboard/layout';
import { SkipLink } from '@/components/layout/skip-link';
import { useAuth } from '@/lib/auth-context';
import { usePathname, useRouter } from 'next/navigation';
vi.mock('next/navigation', () => ({usePathname:vi.fn(),useRouter:vi.fn()}));
vi.mock('@/lib/auth-context', () => ({useAuth:vi.fn()}));
vi.mock('@/components/dashboard/breadcrumb', () => ({DashboardBreadcrumb:()=>null}));
vi.mock('@/hooks/use-api', () => ({useSystemStatus:()=>({})}));
const push = vi.fn(), replace = vi.fn(), logout = vi.fn();
let auth: any;
const Page = () => <><SkipLink/><DashboardLayout><button>Protected work</button></DashboardLayout></>;
beforeEach(() => {
 vi.clearAllMocks(); localStorage.clear();
 vi.mocked(usePathname).mockReturnValue('/dashboard');
 vi.mocked(useRouter).mockReturnValue({push,replace} as any);
 auth = {isHydrated:true,isAuthenticated:true,logout,user:{email:'operator@example.com'}};
 vi.mocked(useAuth).mockImplementation(()=>auth);
});
describe('dashboard shell interactions', () => {
 it('keeps native links and excludes collapsed destinations', () => {
  render(<Page/>);
  const nav = screen.getByRole('navigation',{name:'Dashboard navigation'});
  expect(within(nav).getByRole('link',{name:'Overview'})).toBeInTheDocument();
  expect(within(nav).queryByRole('link',{name:'Import files'})).toBeNull();
  const toggle = within(nav).getByRole('button',{name:'Intake'});
  expect(toggle).toHaveAttribute('aria-controls');
  fireEvent.click(toggle);
  expect(within(nav).getByRole('link',{name:'Import files'})).toBeInTheDocument();
  fireEvent.click(toggle);
  expect(within(nav).queryByText('Import files')).toBeNull();
 });
 it.each(['/dashboard', '/requests', '/records/record-1'])('focuses content after repeated navigation on %s', (pathname) => {
  vi.mocked(usePathname).mockReturnValue(pathname);
  render(<Page/>);
  fireEvent.click(screen.getByRole('link',{name:'Skip to content'}));
  expect(document.activeElement).toBe(document.getElementById('dashboard-main-content'));
  expect(document.activeElement).toContainElement(screen.getByRole('button',{name:'Protected work'}));
 });
 it('uses modal initial and returned focus and closes same-route navigation', async () => {
  const user = userEvent.setup(); render(<Page/>);
  const trigger = screen.getByRole('button',{name:'Open navigation menu'});
  await user.click(trigger);
  const dialog = screen.getByRole('dialog',{name:'Dashboard navigation menu'});
  expect(dialog).toContainElement(document.activeElement as HTMLElement);
  for (let i=0;i<25;i++) { await user.tab(); expect(dialog).toContainElement(document.activeElement as HTMLElement); }
  for (let i=0;i<3;i++) { await user.tab({shift:true}); expect(dialog).toContainElement(document.activeElement as HTMLElement); }
  expect(within(dialog).getByRole('button',{name:'Sign Out'})).toBeInTheDocument();
  await user.keyboard('{Escape}');
  await waitFor(()=>expect(trigger).toHaveFocus());
  await user.click(trigger);
  await user.click(within(screen.getByRole('dialog')).getByRole('link',{name:'Overview'}));
  await waitFor(()=>expect(screen.queryByRole('dialog')).toBeNull());
  expect(document.getElementById('dashboard-main-content')).toHaveFocus();
 });
 it('keeps failed sign-out retry available after sensitive local state is cleared', async () => {
  let reject!: (error: Error)=>void;
  logout.mockImplementationOnce(()=>new Promise((_resolve, fail)=>{reject=fail})).mockResolvedValueOnce(undefined);
  const {rerender} = render(<Page/>);
  fireEvent.click(screen.getByRole('button',{name:'Sign Out'}));
  expect(screen.getByRole('button',{name:'Signing out…'})).toBeDisabled();
  fireEvent.click(screen.getByRole('button',{name:'Signing out…'}));
  expect(logout).toHaveBeenCalledTimes(1);
  auth={...auth,isAuthenticated:false,user:null}; rerender(<Page/>);
  expect(screen.queryByText('Protected work')).toBeNull();
  await act(async()=>reject(new Error('backend detail')));
  expect(screen.getByRole('alert')).toHaveTextContent('Sign-out could not be confirmed. Please retry.');
  expect(push).not.toHaveBeenCalled(); expect(replace).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole('button',{name:'Sign Out'}));
  await waitFor(()=>expect(replace).toHaveBeenCalledWith('/login'));
  expect(logout).toHaveBeenCalledTimes(2);
 });
 it('shows the same pending and failed action in the mobile dialog', async () => {
  logout.mockRejectedValue(new Error('unconfirmed'));
  const user=userEvent.setup(); render(<Page/>);
  await user.click(screen.getByRole('button',{name:'Open navigation menu'}));
  await user.click(within(screen.getByRole('dialog')).getByRole('button',{name:'Sign Out'}));
  expect(within(screen.getByRole('dialog')).getByRole('alert')).toHaveTextContent('Sign-out could not be confirmed');
  expect(within(screen.getByRole('dialog')).getByRole('button',{name:'Sign Out'})).toBeEnabled();
 });
});
