import { Metadata } from "next";
import { DrillSimulatorClient } from "./components/DrillSimulatorClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "24-Hour Drill Simulator | FSMA 204 Outbreak Quest | RegEngine",
    description: "A scenario-based quest to see if your manual processes can survive a real FDA outbreak investigation. Test your record retrieval speed and compliance accuracy.",
    openGraph: {
        title: "24-Hour Drill Simulator — RegEngine",
        description: "Test your FDA outbreak response speed.",
        type: "website",
        url: "https://www.regengine.co/tools/drill-simulator",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "24-Hour Drill Simulator",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Scenario-based simulation for FSMA 204 record retrieval drills.",
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

export default function DrillSimulatorPage() {
    return (
        <>
            <JSONLD data={jsonLd} />
            <DrillSimulatorClient />
        </>
    );
}
