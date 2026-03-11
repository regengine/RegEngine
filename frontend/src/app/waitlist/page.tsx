import { Suspense } from 'react';
import WaitlistPage from './WaitlistClient';

export default function WaitlistPageWrapper() {
    return (
        <Suspense>
            <WaitlistPage />
        </Suspense>
    );
}
