import { Metadata } from "next";
import { SelfReportedChecklistClient } from "./components/SelfReportedChecklistClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";

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
            <div className="min-h-screen bg-[var(--re-surface-base)] px-6 py-16">
                <div className="max-w-2xl mx-auto text-center">
                    <h1 className="text-2xl font-bold text-[var(--re-text-primary)] mb-3">Self-Reported Checklist</h1>
                    <p className="text-sm text-[var(--re-text-muted)] max-w-lg mx-auto mb-8 leading-relaxed">
                        You answer. We echo what you reported. We do not verify records, we do not score readiness, and we do not decide whether you can meet §1.1455.
                    </p>
                    <div className="flex gap-2 items-center justify-center text-xs text-[var(--re-text-disabled)]">
                        <div className="w-3 h-3 rounded-full border-2 border-re-brand border-t-transparent animate-spin" />
                        Loading checklist…
                    </div>
                </div>
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
