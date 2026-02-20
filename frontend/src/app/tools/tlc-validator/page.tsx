import { Metadata } from "next";
import { TLCValidatorClient } from "./components/TLCValidatorClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "TLC Validator | GS1 Traceability Lot Code Checker | RegEngine",
    description: "Stress-test your Traceability Lot Code (TLC) format against GS1 standards and FDAs requirement for uniqueness. Professional data integrity tool for FSMA 204.",
    openGraph: {
        title: "TLC Validator — RegEngine",
        description: "Validate your GS1 Traceability Lot Codes.",
        type: "website",
        url: "https://regengine.vercel.app/tools/tlc-validator",
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
        <div className="min-h-screen py-10 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-base)]">
            <JSONLD data={jsonLd} />
            <div className="max-w-7xl mx-auto">
                <Breadcrumbs
                    items={[
                        { label: "Free Tools", href: "/tools" },
                        { label: "TLC Validator" }
                    ]}
                />
                <TLCValidatorClient />
            </div>
        </div>
    );
}
