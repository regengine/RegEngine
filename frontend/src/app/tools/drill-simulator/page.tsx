import { Metadata } from "next";
import { DrillSimulatorClient } from "./components/DrillSimulatorClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";

export const metadata: Metadata = {
    title: "24-Hour Drill Simulator | Practice FSMA 204 FDA Outbreak Response | RegEngine",
    description: "Run a scenario-based FDA outbreak drill to test if your manual processes can meet the 24-hour records retrieval mandate. Free FSMA 204 compliance simulation.",
    alternates: {
        canonical: "https://www.regengine.co/tools/drill-simulator",
    },
    openGraph: {
        title: "24-Hour Drill Simulator — RegEngine",
        description: "Simulate an FDA outbreak investigation to test your FSMA 204 record retrieval speed and compliance accuracy. Free.",
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
            <EmailGate toolName="drill-simulator">
                <DrillSimulatorClient />
            </EmailGate>
            <RelatedTools tools={[
                { href: "/tools/recall-readiness", title: "Recall Readiness Score", description: "Get an A–F grade on your FDA 24-hour records retrieval readiness." },
                { href: "/tools/notice-validator", title: "FDA Request Validator", description: "Validate a draft FDA response against FSMA 204 record requirements." },
                { href: "/tools/readiness-assessment", title: "Readiness Assessment", description: "Score your full FSMA 204 compliance posture across all requirement areas." },
            ]} />
        </>
    );
}
