import { Metadata } from "next";
import { Suspense } from "react";
import { KDECheckerClient } from "./components/KDECheckerClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { Container } from "@/components/layout/container";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
    title: "KDE Checklist Builder | FSMA 204 Starting Checklist | RegEngine",
    description: "Generate a starting KDE checklist mapped to your FTL product and trading role under 21 CFR Part 1 Subpart S. Educational; verify against the rule and consult counsel before relying on it.",
    alternates: {
        canonical: "https://regengine.co/tools/kde-checker",
    },
    openGraph: {
        title: "KDE Checklist Builder — RegEngine",
        description: "Generate a starting KDE checklist mapped to your FTL product and trading role. Educational; not a regulatory determination.",
        type: "website",
        url: "https://regengine.co/tools/kde-checker",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "KDE Completeness Checker",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Starting Key Data Element (KDE) checklist mapped to your FTL product and trading role. Educational; not a regulatory determination.",
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

function KDECheckerFallback() {
    return (
        <div className="mx-auto max-w-3xl space-y-4 py-6" aria-busy="true">
            <Skeleton className="h-10 w-2/3 rounded-md" />
            <Skeleton className="h-16 w-full rounded-md" />
            <Skeleton className="h-24 w-full rounded-lg" />
            <Skeleton className="h-11 w-full rounded-md" />
        </div>
    );
}

export default function KDECheckerPage() {
    return (
        <>
            <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
                <JSONLD data={jsonLd} />
                <Container width="tool">
                    <Breadcrumbs
                        items={[
                            { label: "Free Tools", href: "/tools" },
                            { label: "KDE Checker" }
                        ]}
                    />
                    <Suspense fallback={<KDECheckerFallback />}>
                        <EmailGate toolName="kde-checker">
                            <KDECheckerClient />
                        </EmailGate>
                    </Suspense>
                </Container>
            </div>
            <RelatedTools tools={[
                { href: "/tools/cte-mapper", title: "CTE Mapper", description: "Visualize all 7 Critical Tracking Events across your supply chain nodes." },
                { href: "/tools/tlc-validator", title: "TLC Validator", description: "Validate your Traceability Lot Code format against GS1 and FDA standards." },
                { href: "/tools/ftl-checker", title: "FTL Checker", description: "Check if your food products are on the FDA Food Traceability List." },
            ]} />
        </>
    );
}
