import { cookies } from 'next/headers';
import { redirect } from 'next/navigation';
import { DeveloperPortalShell } from '@/components/developer/DeveloperPortalShell';

export default async function DeveloperPortalLayout({ children }: { children: React.ReactNode }) {
    const cookieStore = await cookies();
    const accessToken = cookieStore.get('re_access_token')?.value;

    if (!accessToken) {
        redirect('/login?next=/developer/portal');
    }

    return <DeveloperPortalShell>{children}</DeveloperPortalShell>;
}
