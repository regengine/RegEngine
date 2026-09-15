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
    title: "TLC Validator | Test Your GS1 Traceability Lot Code Format | RegEngine",
    description: "Stress-test your Traceability Lot Code (TLC) format against GS1 standards and FDA uniqueness requirements. Free data integrity checker for FSMA 204 compliance.",
    alternates: {
        canonical: "https://regengine.co/tools/tlc-validator",
    },
    openGraph: {
        title: "TLC Validator — RegEngine",
        description: "Validate your Traceability Lot Code format against GS1 standards and FDA FSMA 204 requirements. Free.",
        type: "website",
        url: "https://regengine.co/tools/tlc-validator",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "TLC Validator",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "GS1 compatibility and uniqueness validator for Traceability Lot Codes (TLC).",
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

export default function TLCValidatorPage() {
    return (
        <>
            <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
                <JSONLD data={jsonLd} />
                <Container width="tool">
                    <Breadcrumbs
                        items={[
                            { label: "Free Tools", href: "/tools" },
                            { label: "TLC Validator" }
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
                { href: "/tools/kde-checker", title: "KDE Checker", description: "Generate the full Key Data Element checklist required for your product and CTE type." },
                { href: "/tools/ftl-checker", title: "FTL Checker", description: "Confirm your product is on the FDA Food Traceability List before building lot codes." },
                { href: "/tools/export", title: "FDA-Oriented Export Generator", description: "Generate a verifiable records package from your traceability records." },
            ]} />
        </>
    );
}
