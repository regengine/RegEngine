"use client";

import { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { apiClient } from "@/lib/api-client";
import { Loader2, CheckCircle, AlertCircle, UserPlus } from "lucide-react";
import { AuthShell } from "@/components/auth/AuthShell";

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
        description="Your account is ready. We'll email you a sign-in code when you log in — no password needed."
        icon={CheckCircle}
      >
        <div role="status" className="space-y-4 text-center">
          <p className="sr-only">
            Your account is ready. We&apos;ll email you a sign-in code when you
            log in — no password needed.
          </p>
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-[var(--re-success-bg)]">
            <CheckCircle
              className="h-7 w-7 text-re-success"
              aria-hidden="true"
            />
          </div>
          <Button className="w-full" onClick={() => router.push("/login")}>
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
      icon={UserPlus}
    >
      {token === undefined ? (
        <div
          role="status"
          className="flex items-center justify-center gap-2 rounded-md border border-[var(--re-border-subtle)] bg-[var(--re-surface-card)] p-4 text-sm text-[var(--re-text-muted)]"
        >
          <Loader2
            className="h-5 w-5 animate-spin text-[var(--re-brand)]"
            aria-hidden="true"
          />
          <span>Checking invitation...</span>
        </div>
      ) : !token ? (
        <div
          role="alert"
          className="flex items-center gap-2 rounded-md border border-re-danger bg-re-danger-muted p-4 text-sm text-re-danger"
        >
          <AlertCircle className="h-5 w-5" aria-hidden="true" />
          <span>Missing invitation token. Please check your link.</span>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div
              role="alert"
              className="rounded-md border border-re-danger bg-re-danger-muted p-3 text-sm text-re-danger"
            >
              {error}
            </div>
          )}

          <div className="space-y-2">
            <label className="text-sm font-medium" htmlFor="invite-name">
              Full Name
            </label>
            <Input
              id="invite-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="John Doe"
              required
              autoComplete="name"
            />
          </div>

          <Button type="submit" className="w-full" disabled={isLoading}>
            {isLoading ? (
              <span role="status" className="inline-flex items-center">
                <Loader2
                  className="mr-2 h-4 w-4 animate-spin"
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
