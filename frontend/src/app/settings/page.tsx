import { redirect } from 'next/navigation';

// The settings hub lives at /dashboard/settings. next.config.js also 301s the
// bare /settings path; this page-level redirect covers static export and
// direct renders. Sub-pages (/settings/profile, /settings/security,
// /settings/support) keep their own routes; team management moved to
// /dashboard/settings/users.
export default function SettingsRedirectPage() {
    redirect('/dashboard/settings');
}
