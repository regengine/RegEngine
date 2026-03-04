'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';

export default function OnboardingRedirectPage() {
  const router = useRouter();

  useEffect(() => {
    const queryString = typeof window !== 'undefined' ? window.location.search : '';
    router.replace(`/onboarding/supplier-flow${queryString}`);
  }, [router]);

  return (
    <main className="min-h-[50vh] flex items-center justify-center px-6 text-center">
      <p className="text-sm text-slate-600">
        Redirecting to supplier onboarding. If this takes too long, continue to{' '}
        <Link href="/onboarding/supplier-flow" className="font-semibold text-emerald-700 hover:text-emerald-600">
          Supplier Flow
        </Link>
        .
      </p>
    </main>
  );
}
