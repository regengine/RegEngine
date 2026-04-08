import { Metadata } from "next";
import { Suspense } from "react";
import { KDECheckerClient } from "./components/KDECheckerClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";

export const metadata: Metadata = {
    title: "KDE Completeness Checker | FSMA 204 Data Checklist | RegEngine",
    description: "Generate your customized Key Data Element (KDE) checklist based on your specific FTL product and trading role. Ensure compliance with FDA Subpart S.",
    openGraph: {
        title: "KDE Completeness Checker — RegEngine",
        description: "Generate your custom FSMA 204 KDE checklist.",
        type: "website",
        url: "https://www.regengine.co/tools/kde-checker",
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
    );
}
