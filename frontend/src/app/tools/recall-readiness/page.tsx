import { Metadata } from "next";
import { Suspense } from "react";
import { RecallReadinessClient } from "./components/RecallReadinessClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";
import { Container } from "@/components/layout/container";
import { Skeleton } from "@/components/ui/skeleton";

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
            <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
                <JSONLD data={jsonLd} />
                <Container width="tool">
                    <Breadcrumbs
                        items={[
                            { label: "Free Tools", href: "/tools" },
                            { label: "FSMA 204 Readiness Self-Check" }
                        ]}
                    />
                    <Suspense
                        fallback={
                            <div className="space-y-3" role="status" aria-live="polite">
                                <Skeleton className="h-8 w-2/3" />
                                <Skeleton className="h-32 w-full" />
                                <Skeleton className="h-10 w-full" />
                            </div>
                        }
                    >
                        <EmailGate toolName="recall-readiness">
                            <RecallReadinessClient />
                        </EmailGate>
                    </Suspense>
                </Container>
            </div>
            <RelatedTools tools={[
                { href: "/tools/drill-simulator", title: "24-Hour Drill Simulator", description: "Practice a §1.1455(c) records-request drill before a real one." },
                { href: "/tools/readiness-assessment", title: "Readiness Assessment", description: "Score your full FSMA 204 compliance posture across all requirement areas." },
                { href: "/tools/notice-validator", title: "FDA Request Validator", description: "Check whether your draft FDA response covers all required FSMA 204 elements." },
            ]} />
        </>
    );
}
