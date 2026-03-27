'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { Loader2 } from 'lucide-react';

/**
 * Developer registration now redirects to the main app signup.
 * Auth is unified via useAuth() — no separate developer auth flow.
 */
export default function DeveloperRegisterPage() {
    const router = useRouter();

    useEffect(() => {
        router.replace('/signup?next=/developer/portal');
    }, [router]);

    return (
        <div className="min-h-screen flex items-center justify-center" style={{ background: 'var(--re-surface-base)' }}>
            <div className="text-center">
                <Loader2 className="w-6 h-6 animate-spin mx-auto mb-3" style={{ color: 'var(--re-text-muted)' }} />
                <p className="text-sm" style={{ color: 'var(--re-text-muted)' }}>Redirecting to sign up...</p>
            </div>
        </div>
    );
}
