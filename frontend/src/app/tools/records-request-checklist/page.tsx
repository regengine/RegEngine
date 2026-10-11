import { Metadata } from "next";
import { Suspense } from "react";
import { RecordsRequestChecklistClient } from "./components/RecordsRequestChecklistClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";
import { Container } from "@/components/layout/container";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
    title: "FSMA 204 Records Request Checklist | RegEngine",
    description: "A self reported checklist for an FDA records request under 21 CFR 1.1455. Not a 24 hour test, not a readiness score, and not legal advice.",
    alternates: {
        canonical: "https://regengine.co/tools/records-request-checklist",
    },
    openGraph: {
        title: "FSMA 204 Records Request Checklist | RegEngine",
        description: "A self reported checklist for an FDA records request under 21 CFR 1.1455. Not a 24 hour test, not a readiness score, and not legal advice.",
        type: "website",
        url: "https://regengine.co/tools/records-request-checklist",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "Records Request Checklist",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Self-reported checklist for §1.1455 records-request readiness. Not a 24-hour capability test, not a recall-readiness score, and not legal advice.",
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    }
};

export default function RecordsRequestChecklistPage() {
    return (
        <>
            <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
                <JSONLD data={jsonLd} />
                <Container width="tool">
                    <Breadcrumbs
                        items={[
                            { label: "Free Tools", href: "/tools" },
                            { label: "Records Request Checklist" }
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
                        <EmailGate toolName="records-request-checklist">
                            <RecordsRequestChecklistClient />
                        </EmailGate>
                    </Suspense>
                </Container>
            </div>
            <RelatedTools tools={[
                { href: "/tools/ftl-checker", title: "FTL List Checker", description: "Look at the Food Traceability List. This page does not decide if you are a covered person." },
                { href: "/tools/cte-mapper", title: "CTE Mapper", description: "Map the 7 Critical Tracking Events your supply chain must document." },
                { href: "/tools/kde-checker", title: "KDE Field Checklist", description: "Check whether CTE/KDE fields are present for each FTL product and CTE type." },
            ]} />
        </>
    );
}
