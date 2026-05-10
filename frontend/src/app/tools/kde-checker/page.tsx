import { Metadata } from "next";
import { Suspense } from "react";
import { KDECheckerClient } from "./components/KDECheckerClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";

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

export default function KDECheckerPage() {
    return (
        <>
            <div className="min-h-screen py-10 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-base)]">
                <JSONLD data={jsonLd} />
                <div className="max-w-7xl mx-auto">
                    <Breadcrumbs
                        items={[
                            { label: "Free Tools", href: "/tools" },
                            { label: "KDE Checker" }
                        ]}
                    />
                    <Suspense>
                        <EmailGate toolName="kde-checker">
                            <KDECheckerClient />
                        </EmailGate>
                    </Suspense>
                </div>
            </div>
            <RelatedTools tools={[
                { href: "/tools/cte-mapper", title: "CTE Mapper", description: "Visualize all 7 Critical Tracking Events across your supply chain nodes." },
                { href: "/tools/tlc-validator", title: "TLC Validator", description: "Validate your Traceability Lot Code format against GS1 and FDA standards." },
                { href: "/tools/ftl-checker", title: "FTL Checker", description: "Check if your food products are on the FDA Food Traceability List." },
            ]} />
        </>
    );
}
