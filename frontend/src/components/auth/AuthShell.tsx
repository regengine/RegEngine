import Link from "next/link";
import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import { Card } from "@/components/ui/card";
import { RegEngineWordmark } from "@/components/layout/regengine-wordmark";

/**
 * AuthShell — SPEC §6 / proposal-A §6.5.
 *
 * The single shell for /login, /signup, /accept-invite, /auth/verify and the
 * SSO handoff: full-bleed `surface-base` (no grid paper), one centred 400px
 * column starting at 12vh — wordmark, title, description, then the form in a
 * spacious card, then any notice as a Callout *below* the card, then a small
 * link back out. The split "secure access context" rail is gone on every
 * breakpoint.
 */
type AuthShellProps = {
  title: string;
  description: string;
  /**
   * Kept for API compatibility with existing call sites. The template no
   * longer renders an icon tile: SPEC §0 rule 8 forbids an icon before an H1,
   * and rule 7 forbids icons in tinted squares.
   */
  icon?: LucideIcon;
  children: ReactNode;
  /** Notice rendered below the card — a `Callout`, never beside the form. */
  notice?: ReactNode;
  /** `text-small` link back to the site, below the notice. */
  footer?: ReactNode;
  /**
   * `/auth/sso/mock` must expose exactly one link (`/login`) —
   * src/__tests__/lib/prod-inert-gates.test.ts asserts the href set — so that
   * screen suppresses the wordmark's home link.
   */
  showHomeLink?: boolean;
};

export function AuthShell({
  title,
  description,
  children,
  notice,
  footer,
  showHomeLink = true,
}: AuthShellProps) {
  return (
    <div className="min-h-screen overflow-x-hidden bg-re-surface-base text-re-text-primary">
      <div className="mx-auto w-full max-w-[400px] px-4 pb-16 pt-[8vh] sm:pt-[12vh]">
        <div className="mb-8">
          {showHomeLink ? (
            <Link
              href="/"
              className="inline-flex w-fit items-center rounded-md no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset"
            >
              <RegEngineWordmark size="md" />
            </Link>
          ) : (
            <RegEngineWordmark size="md" />
          )}
        </div>

        <h1 className="text-title text-re-text-primary">{title}</h1>
        <p className="mt-2 text-ui text-re-text-secondary">{description}</p>

        <Card padding="spacious" className="mt-6">
          {children}
        </Card>

        {notice ? <div className="mt-4">{notice}</div> : null}
        {footer ? <div className="mt-6 text-small">{footer}</div> : null}
      </div>
    </div>
  );
}
