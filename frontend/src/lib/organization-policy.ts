/** Read-only access check; never probe capability using a policy mutation. */
export async function readOrganizationPolicy(organizationId: string): Promise<{domain_verified:boolean; enforced_auth_policy:'standard'|'sso_only'}> {
  const response = await fetch(`/api/admin/admin/organizations/${encodeURIComponent(organizationId)}/sso-policy`, {
    method: 'GET', credentials:'include', cache:'no-store', signal:AbortSignal.timeout(10_000),
  });
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    if (body?.detail?.code === 'requires_step_up') throw new Error('A passkey or SSO session is required for organization policy access.');
    if (response.status === 403) throw new Error('Organization policy access requires system administrator capability.');
    if (response.status === 401) throw new Error('Your session has expired. Please sign in again.');
    throw new Error('Organization policy is unavailable. Please retry.');
  }
  if (typeof body?.domain_verified !== 'boolean' || !['standard','sso_only'].includes(body?.enforced_auth_policy)) throw new Error('Organization policy response is invalid. Please retry.');
  return body;
}
