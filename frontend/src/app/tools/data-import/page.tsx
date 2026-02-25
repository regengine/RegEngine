import { Metadata } from "next";
import { DataImportClient } from "./components/DataImportClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "Data Import Hub | Upload CSV & IoT Data | RegEngine",
    description: "Import your traceability data into RegEngine via CSV upload, IoT temperature logs, or webhook API. Supports Sensitech TempTale and all FSMA 204 CTE types.",
    openGraph: {
        title: "Data Import Hub — RegEngine",
        description: "Get your supply chain data into RegEngine's traceability engine.",
        type: "website",
        url: "https://regengine.co/tools/data-import",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "RegEngine Data Import Hub",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Import traceability data via CSV, IoT logs, or API for FSMA 204 compliance.",
    "offers": {
        "@type": "Offer",
        "price": "0",
        "priceCurrency": "USD"
    },
};

export default function DataImportPage() {
    return (
        <Suspense fallback={<div>Loading...</div>}>
            <JSONLD data={jsonLd} />
            <DataImportClient />
        </Suspense>
    );
}
