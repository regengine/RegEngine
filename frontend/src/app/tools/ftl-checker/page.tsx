import { Metadata } from "next";
import { FTLCheckerClient } from "./components/FTLCheckerClient";
import { Suspense } from "react";
import { Container } from "@/components/layout/container";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
    title: "FTL List Checker for FSMA 204 | RegEngine",
    description: "Check foods against the FDA Food Traceability List. This free page does not decide who must keep records. Verify every grouping on the current FDA list.",
    alternates: {
        canonical: "https://regengine.co/tools/ftl-checker",
    },
    openGraph: {
        title: "FTL List Checker for FSMA 204 | RegEngine",
        description: "Check foods against the FDA Food Traceability List. This free page does not decide who must keep records. Verify every grouping on the current FDA list.",
        type: "website",
        url: "https://regengine.co/tools/ftl-checker",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "FTL List Checker",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Look at the Food Traceability List. This page does not decide if you are a covered person. Verify every grouping against the current FDA FTL.",
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    }
};

function FTLCheckerSkeleton() {
    return (
        <section className="min-h-screen bg-re-surface-base py-10 sm:py-16" aria-busy="true">
            <Container width="tool">
                {/* Header skeleton */}
                <div className="mb-12 text-center">
                    <Skeleton className="mx-auto mb-4 h-4 w-32 rounded-full" />
                    <Skeleton className="mx-auto mb-3 h-8 w-64 rounded-md" />
                    <Skeleton className="mx-auto h-4 w-full max-w-sm rounded-md" />
                </div>

                {/* Search bar skeleton */}
                <Card padding="spacious" className="mb-8">
                    <Skeleton className="mb-3 h-5 w-40 rounded-md" />
                    <Skeleton className="h-12 w-full rounded-md" />
                </Card>

                {/* Category cards skeleton */}
                <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                    {Array.from({ length: 6 }).map((_, i) => (
                        <Card key={i} padding="compact">
                            <Skeleton className="mb-2 h-4 w-20 rounded-md" />
                            <Skeleton className="h-3 w-full rounded-md" />
                        </Card>
                    ))}
                </div>
            </Container>
        </section>
    );
}

export default function FTLCheckerPage() {
    return (
        <>
            <Suspense fallback={<FTLCheckerSkeleton />}>
                <JSONLD data={jsonLd} />
                <EmailGate toolName="ftl-checker">
                    <FTLCheckerClient />
                </EmailGate>
            </Suspense>
            <RelatedTools tools={[
                { href: "/tools/cte-mapper", title: "CTE Mapper", description: "Map the 7 Critical Tracking Events your supply chain often records under FSMA 204." },
                { href: "/tools/kde-checker", title: "KDE Field Checklist", description: "Check whether CTE/KDE fields are present for each FTL product and CTE type." },
            ]} />
        </>
    );
}
