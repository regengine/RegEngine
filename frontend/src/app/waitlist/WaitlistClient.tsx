'use client';

import { Suspense } from 'react';
import { useSearchParams } from 'next/navigation';
import { WaitlistGate } from '@/components/ui/waitlist-gate';

function WaitlistContent() {
    const searchParams = useSearchParams();
    const featureNameParam = searchParams.get('feature');

    const featureName = featureNameParam
        ? featureNameParam.charAt(0).toUpperCase() + featureNameParam.slice(1)
        : 'Industry';

    return <WaitlistGate featureName={featureName} />;
}

export default function WaitlistPage() {
    return (
        <Suspense fallback={<div className="min-h-screen bg-[#06090f]" />}>
            <WaitlistContent />
        </Suspense>
    );
}
