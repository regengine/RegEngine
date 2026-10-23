"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Callout } from "@/components/ui/callout";
import { Field } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api-client";
import { Loader2 } from "lucide-react";
import { AuthShell } from "@/components/auth/AuthShell";
import { cn } from "@/lib/utils";

/** Spinner shaped like a Callout icon, so the pending state uses the same row. */
function SpinnerIcon({ className }: { className?: string }) {
  return (
    <Loader2
      className={cn(className, "animate-spin motion-reduce:animate-none")}
      aria-hidden="true"
    />
  );
}

function readInviteTokenFromLocation(): string | null {
  if (typeof window === "undefined") return null;

  const hashParams = new URLSearchParams(
    window.location.hash.replace(/^#/, ""),
  );
  const hashToken = hashParams.get("token");
  if (hashToken) return hashToken;

  return new URLSearchParams(window.location.search).get("token");
}

function scrubSensitiveInviteUrl(): void {
  if (typeof window === "undefined") return;

  const url = new URL(window.location.href);
  const hashParams = new URLSearchParams(url.hash.replace(/^#/, ""));
  const hasSensitiveParams =
    url.searchParams.has("token") ||
    url.searchParams.has("email") ||
    hashParams.has("token");
  if (!hasSensitiveParams) return;

  url.searchParams.delete("token");
  url.searchParams.delete("email");
  url.hash = "";
  window.history.replaceState(
    null,
    document.title,
    `${url.pathname}${url.search}`,
  );
}

export default function AcceptInvitePage() {
  const router = useRouter();

  const [isLoading, setIsLoading] = useState(false);
  const [step, setStep] = useState<"verify" | "form" | "success">("form");
  const [error, setError] = useState<string | null>(null);
  const [token, setToken] = useState<string | null | undefined>(undefined);

  const [name, setName] = useState("");

  useEffect(() => {
    const inviteToken = readInviteTokenFromLocation();
    setToken(inviteToken);
    scrubSensitiveInviteUrl();
    if (!inviteToken) {
      setError("Invalid invitation link.");
    }
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    setIsLoading(true);
    try {
      if (!token) {
        setError("Invalid invitation link.");
        return;
      }

      await apiClient.acceptInvite({
        token,
        name,
      });

      setStep("success");
    } catch (err: unknown) {
      if (process.env.NODE_ENV !== "production") {
        console.error(err);
      }
      const axiosError = err as { response?: { data?: { detail?: string } } };
      if (axiosError?.response?.data?.detail) {
        setError(axiosError.response.data.detail);
      } else {
        setError(
          "Failed to accept invite. It may have expired or been revoked.",
        );
      }
    } finally {
      setIsLoading(false);
    }
  };

  if (step === "success") {
    return (
      <AuthShell
        title="Welcome aboard"
        description="Your account is ready. We'll email you a sign-in code when you log in. No password needed."
      >
        <div role="status" className="space-y-4">
          <p className="sr-only">
            Your account is ready. We&apos;ll email you a sign-in code when you
            log in. No password needed.
          </p>
          <Button
            className="w-full"
            size="lg"
            onClick={() => router.push("/login")}
          >
            Go to Login
          </Button>
        </div>
      </AuthShell>
    );
  }

  return (
    <AuthShell
      title="Accept invitation"
      description="Create your account to join the workspace."
    >
      {token === undefined ? (
        <Callout role="status" icon={SpinnerIcon}>
          Checking invitation...
        </Callout>
      ) : !token ? (
        <Callout tone="danger" role="alert">
          Missing invitation token. Please check your link.
        </Callout>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <Callout tone="danger" role="alert">
              {error}
            </Callout>
          )}

          <Field label="Full Name" htmlFor="invite-name">
            <Input
              id="invite-name"
              size="lg"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="John Doe"
              required
              autoComplete="name"
            />
          </Field>

          <Button type="submit" className="w-full" size="lg" disabled={isLoading}>
            {isLoading ? (
              <span role="status" className="inline-flex items-center">
                <Loader2
                  className="mr-2 h-4 w-4 animate-spin motion-reduce:animate-none"
                  aria-hidden="true"
                />
                Creating account...
              </span>
            ) : (
              "Create Account"
            )}
          </Button>
        </form>
      )}
    </AuthShell>
  );
}
