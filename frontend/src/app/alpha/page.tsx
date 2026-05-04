import { redirect } from 'next/navigation';

export default function AlphaRedirect() {
    redirect('/signup?partner=founding');
}
