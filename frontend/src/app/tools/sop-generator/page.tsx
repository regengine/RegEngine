import { Metadata } from "next";
import { SOPGeneratorClient } from "./components/SOPGeneratorClient";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";

export const metadata: Metadata = {
    title: "FSMA 204 SOP Generator | Auto-Generate Your Traceability Plan | RegEngine",
    description: "Auto-generate your FSMA 204 Traceability Plan and Standard Operating Procedures in minutes. Customized for your company, products, and supply chain role. Free.",
    alternates: {
        canonical: "https://regengine.co/tools/sop-generator",
    },
    openGraph: {
        title: "FSMA 204 SOP Generator — RegEngine",
        description: "Auto-generate a complete FSMA 204 Traceability Plan and SOPs for your company. Download free.",
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
            <RelatedTools tools={[
                { href: "/tools/readiness-assessment", title: "Readiness Assessment", description: "Score your FSMA 204 compliance posture before generating your traceability plan." },
                { href: "/tools/cte-mapper", title: "CTE Mapper", description: "Map the Critical Tracking Events your SOPs need to cover across your supply chain." },
                { href: "/tools/kde-checker", title: "KDE Checker", description: "Generate the Key Data Element checklist to include in your traceability procedures." },
            ]} />
        </>
    );
}
