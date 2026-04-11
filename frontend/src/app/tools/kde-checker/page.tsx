import { Metadata } from "next";
import { Suspense } from "react";
import { KDECheckerClient } from "./components/KDECheckerClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";

export const metadata: Metadata = {
    title: "KDE Checker | FSMA 204 Key Data Element Completeness Tool | RegEngine",
    description: "Generate a customized Key Data Element (KDE) checklist based on your FTL product and trading role. Ensure full FDA Subpart S compliance. Free FSMA 204 tool.",
    alternates: {
        canonical: "https://regengine.co/tools/kde-checker",
    },
    openGraph: {
        title: "KDE Checker — RegEngine",
        description: "Generate a customized FSMA 204 Key Data Element checklist for your product and trading role. Free.",
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
    "description": "Customized Key Data Element (KDE) generator for FSMA 204 compliance.",
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
