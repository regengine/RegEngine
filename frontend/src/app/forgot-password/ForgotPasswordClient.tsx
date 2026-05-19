"use client";

import { useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { fetchWithCsrf } from "@/lib/fetch-with-csrf";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Loader2, Mail, ShieldCheck, ArrowLeft } from "lucide-react";
import Link from "next/link";
import { AuthShell } from "@/components/auth/AuthShell";

export default function ForgotPasswordClient() {
  const [email, setEmail] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitted, setSubmitted] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();
  const linkExpired = searchParams.get("error") === "link_expired";

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    const trimmed = email.trim();
    if (!trimmed) {
      setError("Email is required.");
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const res = await fetchWithCsrf("/api/admin/auth/forgot-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email: trimmed }),
      });

      if (!res.ok) {
        setError("Failed to send reset email. Please try again.");
        return;
      }

      setSubmitted(true);
    } catch {
      setError("An unexpected error occurred. Please try again.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthShell
      title="Reset your password"
      description="Enter your email and we'll send a reset link."
      icon={Mail}
    >
      {linkExpired && !submitted && (
        <div
          role="alert"
          className="mb-4 rounded-md border border-re-warning bg-re-warning-muted p-3 text-sm text-re-warning dark:border-re-warning dark:bg-re-warning/10 dark:text-re-warning"
        >
          Your reset link has expired. Enter your email to receive a new one.
        </div>
      )}
      {submitted ? (
        <div role="status" className="space-y-5 text-center">
          <div className="mx-auto flex h-14 w-14 items-center justify-center rounded-full bg-re-brand-muted">
            <ShieldCheck className="h-7 w-7 text-re-brand" aria-hidden="true" />
          </div>
          <div className="space-y-1">
            <p className="font-medium text-[var(--re-text-primary)]">
              Check your inbox
            </p>
            <p className="text-sm text-[var(--re-text-muted)]">
              If{" "}
              <span className="font-mono text-[var(--re-text-secondary)]">
                {email}
              </span>{" "}
              is registered, you&apos;ll receive a reset link within a minute.
            </p>
          </div>
          <p className="text-xs text-[var(--re-text-muted)]">
            The link expires in 1 hour. Check your spam folder if you don&apos;t
            see it.
          </p>
          <Button
            variant="outline"
            className="w-full"
            onClick={() => router.push("/login")}
          >
            Back to sign in
          </Button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div
              role="alert"
              aria-live="polite"
              className="animate-in fade-in slide-in-from-top-2 rounded-md border border-re-danger bg-re-danger-muted p-3 text-sm text-re-danger dark:border-re-danger dark:bg-re-danger/10"
            >
              {error}
            </div>
          )}

          <div className="space-y-2">
            <label
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
              htmlFor="email"
            >
              Email
            </label>
            <Input
              id="email"
              type="email"
              placeholder="name@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              disabled={isLoading}
              required
              autoComplete="email"
              autoFocus
              className="h-11"
            />
          </div>

          <Button className="h-11 w-full" type="submit" disabled={isLoading}>
            {isLoading ? (
              <span role="status" className="inline-flex items-center">
                <Loader2
                  className="mr-2 h-4 w-4 animate-spin"
                  aria-hidden="true"
                />
                Sending reset link...
              </span>
            ) : (
              "Send reset link"
            )}
          </Button>

          <Link
            href="/login"
            className="flex items-center justify-center gap-1 text-sm text-[var(--re-text-muted)] transition hover:text-[var(--re-brand)]"
          >
            <ArrowLeft className="h-3.5 w-3.5" aria-hidden="true" />
            Back to sign in
          </Link>
        </form>
      )}
    </AuthShell>
  );
}
