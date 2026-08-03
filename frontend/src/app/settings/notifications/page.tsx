import { redirect } from 'next/navigation';

// The live notification preferences page is /dashboard/notifications.
// The disabled mock that previously lived here was removed (copy PR-11).
export default function NotificationsRedirectPage() {
    redirect('/dashboard/notifications');
}
