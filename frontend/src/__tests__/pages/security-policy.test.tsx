import { act, cleanup, fireEvent, render, screen } from '@testing-library/react';
import { afterEach, expect, it, vi } from 'vitest';
import Security from '@/app/settings/security/page';
const auth = vi.hoisted(() => ({authMethod:'webauthn',isHighAssuranceSession:true,tenantId:'org-a',user:{id:'user-a',email:'other@example.test'}}));
vi.mock('@/lib/auth-context', () => ({useAuth: () => auth}));
vi.mock('@/lib/passwordless-auth', () => ({registerPasskey:vi.fn()}));
afterEach(() => {cleanup(); auth.tenantId = 'org-a'; auth.user.id = 'user-a'; vi.unstubAllGlobals();});
it('verifies policy with GET alone and displays unchanged verified SSO policy', async () => {
 const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({domain_verified:true,enforced_auth_policy:'sso_only'})));
 vi.stubGlobal('fetch',fetchMock);
 render(<Security />);
 fireEvent.click(screen.getByRole('button',{name:'Verify admin policy access'}));
 expect(await screen.findByText(/Current policy: sso_only; domain verified/)).toBeInTheDocument();
 expect(fetchMock).toHaveBeenCalledTimes(1);
 expect(fetchMock).toHaveBeenCalledWith('/api/admin/admin/organizations/org-a/sso-policy',expect.objectContaining({method:'GET'}));
});
it('explains capability denial instead of misreporting a passkey failure', async () => {
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({detail:'System administrator access required.'}),{status:403})));
 render(<Security />);
 fireEvent.click(screen.getByRole('button',{name:'Verify admin policy access'}));
 expect(await screen.findByText(/requires system administrator capability/)).toBeInTheDocument();
});

it('a deferred organization A result cannot publish after switching to B', async () => {
 let resolve!: (value:Response) => void;
 const response = new Promise<Response>(r => {resolve=r;});
 vi.stubGlobal('fetch',vi.fn().mockReturnValue(response));
 const view = render(<Security />);
 fireEvent.click(screen.getByRole('button',{name:'Verify admin policy access'}));
 auth.tenantId = 'org-b'; view.rerender(<Security />);
 await act(async () => {resolve(new Response(JSON.stringify({domain_verified:true,enforced_auth_policy:'sso_only'})));await response;});
 expect(screen.queryByText(/Current policy: sso_only/)).not.toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Verify admin policy access'})).toBeEnabled();
});
it('a previously confirmed policy disappears when organization changes', async () => {
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({domain_verified:true,enforced_auth_policy:'sso_only'}))));
 const view = render(<Security />);
 fireEvent.click(screen.getByRole('button',{name:'Verify admin policy access'}));
 await screen.findByText(/Current policy: sso_only/);
 auth.tenantId = 'org-b';view.rerender(<Security />);
 expect(screen.queryByText(/Current policy: sso_only/)).not.toBeInTheDocument();
});

it('an account change in the same organization discards a deferred policy check', async () => {
 let resolve!: (value:Response) => void;
 const response = new Promise<Response>(r => {resolve=r;});
 vi.stubGlobal('fetch',vi.fn().mockReturnValue(response));
 const view = render(<Security />);
 fireEvent.click(screen.getByRole('button',{name:'Verify admin policy access'}));
 auth.user.id = 'user-b'; view.rerender(<Security />);
 await act(async () => {resolve(new Response(JSON.stringify({domain_verified:true,enforced_auth_policy:'sso_only'})));await response;});
 expect(screen.queryByText(/Current policy: sso_only/)).not.toBeInTheDocument();
 expect(screen.getByRole('button',{name:'Verify admin policy access'})).toBeEnabled();
});
