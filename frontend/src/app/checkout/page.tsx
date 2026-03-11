import { Suspense } from 'react';
import CheckoutPage from './CheckoutClient';

export default function CheckoutPageWrapper() {
    return (
        <Suspense>
            <CheckoutPage />
        </Suspense>
    );
}
