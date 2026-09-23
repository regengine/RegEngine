import { Metadata } from "next";
import { DrillSimulatorClient } from "./components/DrillSimulatorClient";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";

export const metadata: Metadata = {
    title: "24-Hour Drill Simulator | FSMA 204 §1.1455(c) Records-Request Rehearsal | RegEngine",
    description: "Self-paced rehearsal for the §1.1455(c) records-on-request workflow. Educational; not an FDA simulation and not a compliance determination.",
    alternates: {
        canonical: "https://regengine.co/tools/drill-simulator",
    },
    openGraph: {
        title: "24-Hour Drill Simulator — RegEngine",
        description: "Self-paced rehearsal for the §1.1455(c) records-on-request workflow. Educational; not a compliance determination.",
        type: "website",
        url: "https://regengine.co/tools/drill-simulator",
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
                { href: "/tools/recall-readiness", title: "FSMA 204 Readiness Self-Check", description: "Self-check your readiness for the §1.1455(c) records-on-request obligation." },
                { href: "/tools/notice-validator", title: "FDA Request Validator", description: "Validate a draft FDA response against FSMA 204 record requirements." },
                { href: "/tools/readiness-assessment", title: "Readiness Assessment", description: "Score your full FSMA 204 compliance posture across all requirement areas." },
            ]} />
        </>
    );
}
