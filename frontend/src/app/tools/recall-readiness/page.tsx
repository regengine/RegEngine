import { Metadata } from "next";
import { Suspense } from "react";
import { RecallReadinessClient } from "./components/RecallReadinessClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";

export const metadata: Metadata = {
    title: "FSMA 204 Readiness Self-Check | RegEngine",
    description: "A self-reported readiness self-check for FSMA 204 traceability records. Educational; not a compliance certification.",
    alternates: {
        canonical: "https://regengine.co/tools/recall-readiness",
    },
    openGraph: {
        title: "FSMA 204 Readiness Self-Check — RegEngine",
        description: "A self-reported readiness self-check for FSMA 204 traceability records. Educational; not a compliance certification.",
        type: "website",
        url: "https://regengine.co/tools/recall-readiness",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "FSMA 204 Readiness Self-Check",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "A self-reported readiness self-check for FSMA 204 traceability records. Educational; not a compliance certification.",
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

export default function RecallReadinessPage() {
    return (
        <>
            <div className="min-h-screen py-10 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-base)]">
                <JSONLD data={jsonLd} />
                <div className="max-w-7xl mx-auto">
                    <Breadcrumbs
                        items={[
                            { label: "Free Tools", href: "/tools" },
                            { label: "FSMA 204 Readiness Self-Check" }
                        ]}
                    />
                    <Suspense>
                        <EmailGate toolName="recall-readiness">
                            <RecallReadinessClient />
                        </EmailGate>
                    </Suspense>
                </div>
            </div>
            <RelatedTools tools={[
                { href: "/tools/drill-simulator", title: "24-Hour Drill Simulator", description: "Practice a §1.1455(c) records-request drill before a real one." },
                { href: "/tools/readiness-assessment", title: "Readiness Assessment", description: "Score your full FSMA 204 compliance posture across all requirement areas." },
                { href: "/tools/notice-validator", title: "FDA Request Validator", description: "Check whether your draft FDA response covers all required FSMA 204 elements." },
            ]} />
        </>
    );
}
