import { Metadata } from "next";
import { FTLCheckerClient } from "./components/FTLCheckerClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "FTL Coverage Checker | FDA FSMA 204 Compliance Tool | RegEngine",
    description: "Free FDA Food Traceability List checker. Verify FSMA 204 coverage for your products.",
    openGraph: {
        title: "FTL Coverage Checker — RegEngine",
        description: "Free FDA Food Traceability List checker. Verify FSMA 204 coverage for your products.",
        type: "website",
        url: "https://www.regengine.co/tools/ftl-checker",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "FTL Coverage Checker",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Instantly verify if your food products are covered by FDA FSMA 204 requirements.",
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

export default function FTLCheckerPage() {
    return (
        <Suspense fallback={<div>Loading...</div>}>
            <JSONLD data={jsonLd} />
            <FTLCheckerClient />
        </Suspense>
    );
}
