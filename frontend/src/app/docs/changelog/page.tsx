import type { Metadata } from 'next';
import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';
import { PageHeader } from '@/components/layout/page-header';
import { Badge } from '@/components/ui/badge';

export const metadata: Metadata = {
    title: 'Changelog | RegEngine',
    description:
        'Latest RegEngine product updates, API improvements, and FSMA 204 compliance workflow releases.',
    openGraph: {
      title: 'Changelog',
      description: 'Latest RegEngine product updates, API improvements, and FSMA 204 compliance workflow releases.',
      url: 'https://regengine.co/docs/changelog',
      type: 'website',
    },
};

/** Inline identifier — SPEC §2.3. */
const CODE =
    'rounded-sm bg-re-surface-inset px-1.5 py-0.5 font-mono text-[0.8125rem] text-re-text-primary';

const LIST = 'mt-3 list-disc space-y-1.5 pl-5 text-ui text-re-text-secondary marker:text-re-text-muted';
const GROUP = 'font-mono text-label uppercase text-re-text-muted';

/**
 * One release. A hairline rule separates releases — a tinted band per version
 * would turn the page into a colour field (SPEC §3.2), and the version stamp is
 * mono because it is a recorded identifier (SPEC §2.3).
 */
function Release({
    version,
    date,
    latest,
    title,
    children,
}: {
    version: string;
    date: string;
    latest?: boolean;
    title: string;
    children: React.ReactNode;
}) {
    return (
        <section className="border-t border-re-border-subtle pt-6">
            <div className="flex flex-wrap items-center gap-3">
                <span className="font-mono text-[0.8125rem] font-medium text-re-text-primary">{version}</span>
                <span className="font-mono text-small text-re-text-tertiary">{date}</span>
                {latest && (
                    <Badge tone="neutral" size="sm">
                        Latest
                    </Badge>
                )}
            </div>

            <h2 className="mt-2 text-heading text-re-text-primary">{title}</h2>

            <div className="mt-4 space-y-5">{children}</div>
        </section>
    );
}

export default function ChangelogPage() {
    return (
        <>
            <PageHeader
                breadcrumbs={
                    <Link
                        href="/docs"
                        className="inline-flex items-center gap-2 text-ui text-re-text-secondary no-underline transition-colors duration-120 hover:text-re-text-primary motion-reduce:transition-none"
                    >
                        <ArrowLeft aria-hidden="true" strokeWidth={1.75} className="h-4 w-4" />
                        Back to Docs
                    </Link>
                }
                title="Changelog"
                description="Latest updates and improvements to RegEngine"
            />

            <div className="space-y-8">
                {/* v1.6.0 — Proof Bundle Verification */}
                <Release version="v1.6.0" date="May 10, 2026" latest title="Proof Bundle Verification">
                    <div>
                        <h4 className={GROUP}>Verification</h4>
                        <ul className={LIST}>
                            <li>Offline verifier now validates the current audit bundle structure, including EPCIS package contents</li>
                            <li>Tampered proof-bundle sample added so evaluators can see failure detection instead of only the happy path</li>
                            <li>Root Docker deploy context and admin proxy routing aligned with the consolidated production surface</li>
                        </ul>
                    </div>
                </Release>

                {/* v1.5.0 — Trust and Safety Copy Sweep */}
                <Release version="v1.5.0" date="May 9, 2026" title="Trust and Safety Sweep">
                    <div>
                        <h4 className={GROUP}>Product Copy</h4>
                        <ul className={LIST}>
                            <li>Outcome-promise language removed across marketing, docs, blog, dashboards, and tool result UIs</li>
                            <li>Self-check tools now use gap-indicated framing instead of A-F grades or pass/fail compliance verdicts</li>
                            <li>DPA, Privacy, and Trust Center subprocessor copy reconciled against current production dependencies</li>
                            <li>Rate-limit and SDK docs corrected to match the backend contract that is actually deployed</li>
                        </ul>
                    </div>
                </Release>

                {/* v1.4.0 — Security and Tenant Isolation Hardening */}
                <Release version="v1.4.0" date="May 9, 2026" title="Security and Tenant Isolation Hardening">
                    <div>
                        <h4 className={GROUP}>Security</h4>
                        <ul className={LIST}>
                            <li>Webhook read endpoints tightened against cross-tenant IDOR and tenant-existence oracle leaks</li>
                            <li>SSRF defenses and IP pinning added for outbound fetch surfaces in ingestion and scheduler workflows</li>
                            <li>Login CSRF origin allowlist and JWT/CSRF key separation hardened in the auth surface</li>
                            <li>Tenant-trust gate promoted to a blocking CI check so cross-tenant regressions cannot reach production</li>
                            <li>Project Sentinel checks added for anchorable signing-asymmetry findings</li>
                        </ul>
                    </div>
                </Release>

                {/* v1.3.0 — Production Auth and Architecture Cleanup */}
                <Release version="v1.3.0" date="April 21, 2026" title="Production Auth and API Cleanup">
                    <div>
                        <h4 className={GROUP}>Platform</h4>
                        <ul className={LIST}>
                            <li>Production login 500 resolved with the v062 Alembic migration path</li>
                            <li>Auth route split started to reduce the large legacy handler into reviewed modules</li>
                            <li>Frontend audit sprint closed navigation, contrast, token, and data-fetching cleanup items</li>
                            <li>Security sweep from April 12 resolved JWT rotation, revocation, and CORS hardening gaps</li>
                        </ul>
                    </div>
                </Release>

                {/* v1.2.0 — Phase 4: Accessibility Polish */}
                <Release version="v1.2.0" date="March 4, 2026" title="Accessibility Polish — WCAG 2.1 AA">
                    <div>
                        <h4 className={GROUP}>♿ Accessibility</h4>
                        <ul className={LIST}>
                            <li>Skip-to-content link and ARIA landmark labels on all pages</li>
                            <li>Keyboard-accessible Free Tools dropdown with Escape/ArrowDown navigation</li>
                            <li>Pricing cards now use radio-group semantics with full keyboard support</li>
                            <li>Developer portal tabs upgraded to WAI-ARIA tablist/tab/tabpanel with arrow-key navigation</li>
                            <li><code className={CODE}>prefers-reduced-motion</code> support across all CSS transitions and Framer Motion animations</li>
                            <li>Touch targets increased to WCAG-compliant 44px minimum</li>
                            <li>Heading hierarchy audit and decorative emoji <code className={CODE}>aria-hidden</code> cleanup</li>
                        </ul>
                    </div>
                </Release>

                {/* v1.1.0 — Phase 3: Onboarding UX Redesign */}
                <Release version="v1.1.0" date="February 20, 2026" title="Onboarding UX Redesign">
                    <div>
                        <h4 className={GROUP}>✨ Features</h4>
                        <ul className={LIST}>
                            <li>New onboarding hub with two-path entry: guided wizard and bulk CSV upload</li>
                            <li>Supplier wizard migrated to dark theme using design tokens</li>
                            <li>Bulk upload page migrated to dark theme for site-wide consistency</li>
                            <li>Onboarding navigation shell with progress indicator and exit-to-home</li>
                            <li>Cross-linking between marketing site, onboarding flow, and dashboard</li>
                        </ul>
                    </div>
                </Release>

                {/* v1.0.0 — Initial Public Release */}
                <Release version="v1.0.0" date="February 5, 2026" title="Initial Public Release">
                    <div>
                        <h4 className={GROUP}>✨ Features</h4>
                        <ul className={LIST}>
                            <li>FSMA 204 compliance module with CTEs and KDEs</li>
                            <li>FDA Request Mode — produces a §1.1455(c) sortable spreadsheet to support your 24-hour response obligation</li>
                            <li>Graph-based supply chain tracing (forward/backward)</li>
                            <li>SHA-256 chained record hashing for tamper detection</li>
                            <li>FTL Checker tool for Food Traceability List verification</li>
                        </ul>
                    </div>

                    <div>
                        <h4 className={GROUP}>📚 Documentation</h4>
                        <ul className={LIST}>
                            <li>API Reference with all endpoints</li>
                            <li>FSMA 204 Integration Guide</li>
                            <li>Quickstart tutorial</li>
                            <li>Authentication guide</li>
                            <li>Error codes reference</li>
                        </ul>
                    </div>
                </Release>
            </div>
        </>
    );
}
