import { Metadata } from "next";
import { Suspense } from "react";
import { KDECheckerClient } from "./components/KDECheckerClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { Container } from "@/components/layout/container";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
    title: "FSMA 204 KDE Field Checklist | RegEngine",
    description: "A starting checklist of Key Data Elements for an FTL food and a Critical Tracking Event. Educational only. Check the rule before you rely on it.",
    alternates: {
        canonical: "https://regengine.co/tools/kde-checker",
    },
    openGraph: {
        title: "FSMA 204 KDE Field Checklist | RegEngine",
        description: "A starting checklist of Key Data Elements for an FTL food and a Critical Tracking Event. Educational only. Check the rule before you rely on it.",
        type: "website",
        url: "https://regengine.co/tools/kde-checker",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "KDE Field Checklist",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Starting Key Data Element (KDE) checklist mapped to your FTL product and trading role. Educational; not a regulatory determination.",
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    }
};

function KDECheckerFallback() {
    return (
        <div className="mx-auto max-w-3xl space-y-4 py-6" aria-busy="true">
            <Skeleton className="h-10 w-2/3 rounded-md" />
            <Skeleton className="h-16 w-full rounded-md" />
            <Skeleton className="h-24 w-full rounded-lg" />
            <Skeleton className="h-11 w-full rounded-md" />
        </div>
    );
}

export default function KDECheckerPage() {
    return (
        <>
            <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
                <JSONLD data={jsonLd} />
                <Container width="tool">
                    <Breadcrumbs
                        items={[
                            { label: "Free Tools", href: "/tools" },
                            { label: "KDE Field Checklist" }
                        ]}
                    />
                    <Suspense fallback={<KDECheckerFallback />}>
                        <EmailGate toolName="kde-checker">
                            <KDECheckerClient />
                        </EmailGate>
                    </Suspense>
                </Container>
            </div>
            <RelatedTools tools={[
                { href: "/tools/cte-mapper", title: "CTE Mapper", description: "Visualize all 7 Critical Tracking Events across your supply chain nodes." },
                { href: "/tools/tlc-validator", title: "TLC Format Check", description: "Check a traceability lot code for format and uniqueness assumptions. FDA does not set one TLC format." },
                { href: "/tools/ftl-checker", title: "FTL Checker", description: "Check if your food products are on the FDA Food Traceability List." },
            ]} />
        </>
    );
}
