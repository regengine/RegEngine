'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';

/**
 * Developer login now redirects to the main app login.
 * Auth is unified via useAuth() — no separate developer auth flow.
 */
export default function DeveloperLoginPage() {
    const router = useRouter();

    useEffect(() => {
        router.replace('/login?next=/developer/portal');
    }, [router]);

    return (
        <div className="flex items-center justify-center bg-re-surface-base py-24">
            <div className="text-center">
                <Loader2
                    className="mx-auto mb-3 h-6 w-6 animate-spin text-re-text-muted motion-reduce:animate-none"
                    strokeWidth={1.75}
                    aria-hidden="true"
                />
                <p className="text-ui text-re-text-tertiary">Redirecting to login...</p>
            </div>
        </div>
    );
}
