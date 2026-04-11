import { Metadata } from "next";
import { Suspense } from "react";
import { TLCValidatorClient } from "./components/TLCValidatorClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";

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
            <div className="min-h-screen py-10 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-base)]">
                <JSONLD data={jsonLd} />
                <div className="max-w-7xl mx-auto">
                    <Breadcrumbs
                        items={[
                            { label: "Free Tools", href: "/tools" },
                            { label: "TLC Validator" }
                        ]}
                    />
                    <Suspense>
                        <EmailGate toolName="tlc-validator">
                            <TLCValidatorClient />
                        </EmailGate>
                    </Suspense>
                </div>
            </div>
            <RelatedTools tools={[
                { href: "/tools/kde-checker", title: "KDE Checker", description: "Generate the full Key Data Element checklist required for your product and CTE type." },
                { href: "/tools/ftl-checker", title: "FTL Checker", description: "Confirm your product is on the FDA Food Traceability List before building lot codes." },
                { href: "/tools/export", title: "FDA Export Generator", description: "Generate a verifiable SHA-256 compliance package from your traceability records." },
            ]} />
        </>
    );
}
