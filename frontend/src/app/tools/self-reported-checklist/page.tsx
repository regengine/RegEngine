import { Metadata } from "next";
import { SelfReportedChecklistClient } from "./components/SelfReportedChecklistClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";
import { Container } from "@/components/layout/container";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
    title: "Self-Reported Checklist | RegEngine",
    description: "You answer. We echo what you reported. We do not verify records, we do not score readiness, and we do not decide whether you can meet §1.1455.",
    alternates: {
        canonical: "https://regengine.co/tools/self-reported-checklist",
    },
    openGraph: {
        title: "Self-Reported Checklist — RegEngine",
        description: "You answer. We echo what you reported. Not a readiness score or regulatory determination.",
        type: "website",
        url: "https://regengine.co/tools/self-reported-checklist",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "Self-Reported Checklist",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "You answer. We echo what you reported. We do not verify records, we do not score readiness, and we do not decide whether you can meet §1.1455.",
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

const relatedTools = [
    { href: "/tools/ftl-checker", title: "FTL List Checker", description: "Look at the Food Traceability List. This page does not decide if you are a covered person." },
    { href: "/tools/cte-mapper", title: "CTE Mapper", description: "Map the 7 Critical Tracking Events your supply chain must document." },
    { href: "/tools/kde-checker", title: "KDE Field Checklist", description: "Check whether CTE/KDE fields are present for each FTL product and CTE type." },
];

export default function SelfReportedChecklistPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
                <Container width="tool">
                    <div className="border-b border-re-border-subtle pb-5">
                        <h1 className="text-title text-re-text-primary">Self-Reported Checklist</h1>
                        <p className="mt-1 max-w-[70ch] text-ui text-re-text-secondary">
                            You answer. We echo what you reported. We do not verify records, we do not score readiness, and we do not decide whether you can meet §1.1455.
                        </p>
                    </div>
                    <div className="mt-6 space-y-3" role="status" aria-live="polite">
                        <Skeleton className="h-10 w-full" />
                        <Skeleton className="h-10 w-full" />
                        <Skeleton className="h-10 w-4/5" />
                        <p className="pt-2 text-small text-re-text-muted">Loading checklist…</p>
                    </div>
                </Container>
            </div>
        }>
            <JSONLD data={jsonLd} />
            <EmailGate toolName="self-reported-checklist">
                <SelfReportedChecklistClient />
            </EmailGate>
            <RelatedTools tools={relatedTools} />
        </Suspense>
    );
}
