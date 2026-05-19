import Link from "next/link";
import type { ReactNode } from "react";
import type { LucideIcon } from "lucide-react";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
} from "@/components/ui/card";
import { RegEngineWordmark } from "@/components/layout/regengine-wordmark";

type AuthShellProps = {
  title: string;
  description: string;
  icon?: LucideIcon;
  children: ReactNode;
};

export function AuthShell({
  title,
  description,
  icon: Icon,
  children,
}: AuthShellProps) {
  return (
    <main className="re-compliance-os min-h-screen overflow-x-hidden bg-[var(--re-surface-base)] text-[var(--re-text-primary)]">
      <section className="mx-auto flex min-h-screen w-full max-w-xl items-center px-4 py-6 sm:px-6">
        <Card className="w-full border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] shadow-lg">
          <CardHeader className="px-5 pb-3 pt-6 text-center sm:px-9 sm:pt-9">
            <Link
              href="/"
              className="mx-auto mb-8 inline-flex w-fit items-center text-[var(--re-text-primary)] no-underline"
            >
              <RegEngineWordmark size="md" />
            </Link>

            {Icon ? (
              <div className="mx-auto mb-5 flex h-12 w-12 items-center justify-center rounded-lg border border-[var(--re-info-border)] bg-[var(--re-info-bg)]">
                <Icon
                  className="h-5 w-5 text-[var(--re-info)]"
                  aria-hidden="true"
                />
              </div>
            ) : null}

            <h1 className="text-3xl font-semibold leading-tight text-[var(--re-text-primary)] sm:text-4xl">
              {title}
            </h1>
            <CardDescription className="mt-2 text-base leading-7 text-[var(--re-text-muted)]">
              {description}
            </CardDescription>
          </CardHeader>
          <CardContent className="px-5 pb-6 sm:px-9 sm:pb-9">
            {children}
          </CardContent>
        </Card>
      </section>
    </main>
  );
}
