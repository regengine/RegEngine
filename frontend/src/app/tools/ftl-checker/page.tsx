import { Metadata } from "next";
import { FTLCheckerClient } from "./components/FTLCheckerClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";

export const metadata: Metadata = {
    title: "FTL Checker | Is Your Food on the FDA Traceability List? | RegEngine",
    description: "Free tool to check if your food products are covered by FDA FSMA 204. Search the Food Traceability List by product name or category. No signup needed.",
    alternates: {
        canonical: "https://regengine.co/tools/ftl-checker",
    },
    openGraph: {
        title: "FTL Checker — RegEngine",
        description: "Free tool to check if your food products are covered by FDA FSMA 204. Search the Food Traceability List by product name or category.",
        type: "website",
        url: "https://regengine.co/tools/ftl-checker",
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
        <>
            <Suspense fallback={<FTLCheckerSkeleton />}>
                <JSONLD data={jsonLd} />
                <EmailGate toolName="ftl-checker">
                    <FTLCheckerClient />
                </EmailGate>
            </Suspense>
            <RelatedTools tools={[
                { href: "/tools/cte-mapper", title: "CTE Mapper", description: "Map the 7 Critical Tracking Events your supply chain must document under FSMA 204." },
                { href: "/tools/kde-checker", title: "KDE Checker", description: "Generate your customized Key Data Element checklist for each FTL product and CTE type." },
                { href: "/tools/readiness-assessment", title: "Readiness Assessment", description: "Score your facility's overall FSMA 204 compliance readiness across all requirement areas." },
            ]} />
        </>
    );
}
