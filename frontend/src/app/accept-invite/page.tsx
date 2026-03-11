import { Suspense } from 'react';
import AcceptInvitePage from './AcceptInviteClient';

export default function AcceptInvitePageWrapper() {
    return (
        <Suspense>
            <AcceptInvitePage />
        </Suspense>
    );
}
