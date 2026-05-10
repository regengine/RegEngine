import { Metadata } from "next";
import { SOPGeneratorClient } from "./components/SOPGeneratorClient";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";

export const metadata: Metadata = {
    title: "FSMA 204 SOP Generator | Draft Traceability Plan Template | RegEngine",
    description: "Auto-generate a starting-template FSMA 204 Traceability Plan and SOP scaffold. Customized to your inputs; review with counsel before adoption — not legal advice.",
    alternates: {
        canonical: "https://regengine.co/tools/sop-generator",
    },
    openGraph: {
        title: "FSMA 204 SOP Generator — RegEngine",
        description: "Auto-generate a draft FSMA 204 Traceability Plan template. Review with counsel before audit or retailer use.",
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
    "description": "Auto-generate starting-template FSMA 204 Traceability Plans. Output is a draft; review with counsel before adoption.",
    "offers": { "@type": "Offer", "price": "0", "priceCurrency": "USD" },
};

export default function SOPGeneratorPage() {
    return (
        <>
            <JSONLD data={jsonLd} />
            <EmailGate toolName="sop-generator">
                <SOPGeneratorClient />
            </EmailGate>
            <RelatedTools tools={[
                { href: "/tools/readiness-assessment", title: "Readiness Assessment", description: "Score your FSMA 204 compliance posture before generating your traceability plan." },
                { href: "/tools/cte-mapper", title: "CTE Mapper", description: "Map the Critical Tracking Events your SOPs need to cover across your supply chain." },
                { href: "/tools/kde-checker", title: "KDE Checker", description: "Generate the Key Data Element checklist to include in your traceability procedures." },
            ]} />
        </>
    );
}
