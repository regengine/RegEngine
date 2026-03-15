import { Metadata } from "next";
import { FTLCheckerClient } from "./components/FTLCheckerClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "FTL Coverage Checker | FDA FSMA 204 Compliance Tool | RegEngine",
    description: "Free FDA Food Traceability List checker. Verify FSMA 204 coverage for your products.",
    openGraph: {
        title: "FTL Coverage Checker — RegEngine",
        description: "Free FDA Food Traceability List checker. Verify FSMA 204 coverage for your products.",
        type: "website",
        url: "https://www.regengine.co/tools/ftl-checker",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "FTL Coverage Checker",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Instantly verify if your food products are covered by FDA FSMA 204 requirements.",
    "offers": {
        "@type": "Offer",
        "price": "0",
        "priceCurrency": "USD"
    },
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    }
};

function FTLCheckerSkeleton() {
    return (
        <section className="min-h-screen py-20 px-4" style={{ background: 'var(--re-surface-base)' }}>
            <div className="max-w-3xl mx-auto animate-pulse">
                {/* Header skeleton */}
                <div className="text-center mb-12">
                    <div className="h-4 w-32 mx-auto mb-4 rounded bg-[var(--re-brand-muted)]" />
                    <div className="h-8 w-80 mx-auto mb-3 rounded bg-[var(--re-surface-elevated)]" />
                    <div className="h-4 w-96 mx-auto rounded bg-[var(--re-surface-elevated)]" />
                </div>

                {/* Search bar skeleton */}
                <div
                    className="rounded-xl border p-6 mb-8"
                    style={{
                        background: 'var(--re-surface-card)',
                        borderColor: 'var(--re-surface-border)',
                    }}
                >
                    <div className="h-5 w-40 mb-3 rounded bg-[var(--re-surface-elevated)]" />
                    <div className="h-12 w-full rounded-lg bg-[var(--re-surface-elevated)]" />
                </div>

                {/* Category cards skeleton */}
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                    {Array.from({ length: 6 }).map((_, i) => (
                        <div
                            key={i}
                            className="rounded-lg border p-4"
                            style={{
                                background: 'var(--re-surface-card)',
                                borderColor: 'var(--re-surface-border)',
                            }}
                        >
                            <div className="h-4 w-20 mb-2 rounded bg-[var(--re-surface-elevated)]" />
                            <div className="h-3 w-full rounded bg-[var(--re-surface-elevated)]" />
                        </div>
                    ))}
                </div>
            </div>
        </section>
    );
}

export default function FTLCheckerPage() {
    return (
        <Suspense fallback={<FTLCheckerSkeleton />}>
            <JSONLD data={jsonLd} />
            <FTLCheckerClient />
        </Suspense>
    );
}
