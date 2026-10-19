import { Metadata } from "next";
import { Suspense } from "react";
import { TLCValidatorClient } from "./components/TLCValidatorClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";
import { Container } from "@/components/layout/container";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
    title: "TLC Format Check for FSMA 204 | RegEngine",
    description: "Check a traceability lot code for format and uniqueness assumptions. FDA does not set one TLC format. This free check is not a compliance determination.",
    alternates: {
        canonical: "https://regengine.co/tools/tlc-validator",
    },
    openGraph: {
        title: "TLC Format Check for FSMA 204 | RegEngine",
        description: "Check a traceability lot code for format and uniqueness assumptions. FDA does not set one TLC format. This free check is not a compliance determination.",
        type: "website",
        url: "https://regengine.co/tools/tlc-validator",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "TLC Format Check",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Check a traceability lot code for format and uniqueness assumptions. FDA does not set one TLC format.",
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    }
};

export default function TLCValidatorPage() {
    return (
        <>
            <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
                <JSONLD data={jsonLd} />
                <Container width="tool">
                    <Breadcrumbs
                        items={[
                            { label: "Free Tools", href: "/tools" },
                            { label: "TLC Format Check" }
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
                        <EmailGate toolName="tlc-validator">
                            <TLCValidatorClient />
                        </EmailGate>
                    </Suspense>
                </Container>
            </div>
            <RelatedTools tools={[
                { href: "/tools/kde-checker", title: "KDE Checker", description: "Generate the full Key Data Element (KDE) checklist required for your product and Critical Tracking Event (CTE) type." },
                { href: "/tools/ftl-checker", title: "FTL Checker", description: "Confirm your product is on the FDA Food Traceability List before building lot codes." },
                { href: "/tools/export", title: "FDA-Oriented Export Generator", description: "Generate a verifiable records package from your traceability records." },
            ]} />
        </>
    );
}
