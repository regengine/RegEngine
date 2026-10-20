import { Suspense } from 'react';
import SignupRequestClient from './SignupRequestClient';

export default function SignupPage() {
  return (
    <Suspense fallback={null}>
      <SignupRequestClient />
    </Suspense>
  );
}
