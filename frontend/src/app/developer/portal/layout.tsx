import { redirect } from 'next/navigation';
import { DeveloperPortalShell } from '@/components/developer/DeveloperPortalShell';
import { createSupabaseServerClient } from '@/lib/supabase/server';

export default async function DeveloperPortalLayout({ children }: { children: React.ReactNode }) {
    const supabase = await createSupabaseServerClient();
    const { data: { user } } = await supabase.auth.getUser();

    if (!user) {
        redirect('/login?next=/developer/portal');
    }

    return <DeveloperPortalShell>{children}</DeveloperPortalShell>;
}
