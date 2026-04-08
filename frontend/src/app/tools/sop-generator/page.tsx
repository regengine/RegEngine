import { Metadata } from "next";
import { SOPGeneratorClient } from "./components/SOPGeneratorClient";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";

export const metadata: Metadata = {
    title: "SOP Generator | FSMA 204 Traceability Plan | RegEngine",
    description: "Auto-generate a complete FSMA 204 Traceability Plan and Standard Operating Procedures customized for your company. Free tool by RegEngine.",
    openGraph: {
        title: "SOP Generator — RegEngine",
        description: "Generate your FSMA 204 Traceability Plan in minutes.",
        type: "website",
        url: "https://regengine.co/tools/sop-generator",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "RegEngine SOP Generator",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Auto-generate FSMA 204 Traceability Plans and Standard Operating Procedures.",
    "offers": { "@type": "Offer", "price": "0", "priceCurrency": "USD" },
};

export default function SOPGeneratorPage() {
    return (
        <>
            <JSONLD data={jsonLd} />
            <EmailGate toolName="sop-generator">
                <SOPGeneratorClient />
            </EmailGate>
        </>
    );
}
