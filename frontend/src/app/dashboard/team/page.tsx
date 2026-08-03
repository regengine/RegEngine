import { redirect } from 'next/navigation';

// Canonical people management lives at /settings/users (API-driven roles and
// invitations). The rival team page that previously lived here was removed
// (copy PR-11).
export default function TeamRedirectPage() {
    redirect('/settings/users');
}
