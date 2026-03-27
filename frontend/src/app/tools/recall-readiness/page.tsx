import { Metadata } from "next";
import { Suspense } from "react";
import { RecallReadinessClient } from "./components/RecallReadinessClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "Recall Readiness Score | FDA 24-Hour Records retrieval | RegEngine",
    description: "Get an A-F grade on your ability to meet the FDA 24-hour records retrieval mandate for FSMA 204. Identify compliance gaps and operational risks.",
    openGraph: {
        title: "Recall Readiness Score — RegEngine",
        description: "Benchmark your 24-hour record retrieval speed.",
        type: "website",
        url: "https://www.regengine.co/tools/recall-readiness",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "Recall Readiness Score",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Compliance benchmarking tool for FDA 24-hour traceability record retrieval.",
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
        <div className="min-h-screen py-10 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-base)]">
            <JSONLD data={jsonLd} />
            <div className="max-w-7xl mx-auto">
                <Breadcrumbs
                    items={[
                        { label: "Free Tools", href: "/tools" },
                        { label: "Recall Readiness Score" }
                    ]}
                />
                <Suspense>
                    <RecallReadinessClient />
                </Suspense>
            </div>
        </div>
    );
}
