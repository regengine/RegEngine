import { Suspense } from 'react';
import PasswordlessEntryClient from './PasswordlessEntryClient';

export default function LoginPageWrapper() {
    return (
        <Suspense>
            <PasswordlessEntryClient />
        </Suspense>
    );
}
