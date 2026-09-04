import { Metadata } from "next";
import { Suspense } from "react";
import { RecordsRequestChecklistClient } from "./components/RecordsRequestChecklistClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";

export const metadata: Metadata = {
    title: "Records-Request Checklist | RegEngine",
    description: "§1.1455 is the FDA records-request rule. Teams often keep a sortable electronic spreadsheet so they can answer a records request. This page is a self-reported checklist. It is not a 24-hour capability test, not a recall-readiness score, and not legal advice.",
    alternates: {
        canonical: "https://regengine.co/tools/records-request-checklist",
    },
    openGraph: {
        title: "Records-Request Checklist — RegEngine",
        description: "§1.1455 is the FDA records-request rule. Self-reported checklist. Not a 24-hour capability test or recall-readiness score.",
        type: "website",
        url: "https://regengine.co/tools/records-request-checklist",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "Records-Request Checklist",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Self-reported checklist for §1.1455 records-request readiness. Not a 24-hour capability test, not a recall-readiness score, and not legal advice.",
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

export default function RecordsRequestChecklistPage() {
    return (
        <>
            <div className="min-h-screen py-10 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-base)]">
                <JSONLD data={jsonLd} />
                <div className="max-w-7xl mx-auto">
                    <Breadcrumbs
                        items={[
                            { label: "Free Tools", href: "/tools" },
                            { label: "Records-Request Checklist" }
                        ]}
                    />
                    <Suspense>
                        <EmailGate toolName="records-request-checklist">
                            <RecordsRequestChecklistClient />
                        </EmailGate>
                    </Suspense>
                </div>
            </div>
            <RelatedTools tools={[
                { href: "/tools/ftl-checker", title: "FTL List Checker", description: "Look at the Food Traceability List. This page does not decide if you are a covered person." },
                { href: "/tools/cte-mapper", title: "CTE Mapper", description: "Map the 7 Critical Tracking Events your supply chain must document." },
                { href: "/tools/kde-checker", title: "KDE Field Checklist", description: "Check whether CTE/KDE fields are present for each FTL product and CTE type." },
            ]} />
        </>
    );
}
