"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/lib/auth-context";

/**
 * Legacy supplier flow route.
 *
 * The previous JSX flow maintained its own auth cookie heuristic and drifted
 * from the current HTTP-only cookie model. Keep the route as a compatibility
 * shim for old links, but send users into the maintained onboarding flow.
 */
export default function SupplierOnboardingFlowRedirect() {
  const router = useRouter();
  const { user, isHydrated } = useAuth();

  useEffect(() => {
    if (!isHydrated) return;
    router.replace(user ? "/onboarding/setup/welcome" : "/signup");
  }, [isHydrated, router, user]);

  return (
    <main className="min-h-[80vh] flex items-center justify-center">
      <div className="animate-pulse text-[var(--re-text-muted)] text-sm">
        Loading...
      </div>
    </main>
  );
}
