import { Metadata } from "next";
import { ToolsLandingClient } from "./components/ToolsLandingClient";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "Free FSMA 204 Compliance Tools & Simulators | RegEngine",
    description: "Benchmark your facility's FSMA 204 readiness with our free interactive tools. FTL checkers, ROI calculators, and exemption wizards. Identify critical compliance gaps in minutes.",
    openGraph: {
        title: "FSMA 204 Free Tools — RegEngine",
        description: "Benchmark your readiness with interactive tools.",
        type: "website",
        url: "https://regengine.vercel.app/tools",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    "name": "FSMA 204 Compliance Toolkit",
    "description": "A collection of free interactive tools for FDA FSMA 204 assessment.",
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    },
    "mainEntity": {
        "@type": "ItemList",
        "itemListElement": [
            { "@type": "ListItem", "position": 1, "url": "https://regengine.vercel.app/tools/ftl-checker", "name": "FTL Coverage Checker" },
            { "@type": "ListItem", "position": 2, "url": "https://regengine.vercel.app/tools/fsma-unified", "name": "Unified FSMA Dashboard" },
            { "@type": "ListItem", "position": 3, "url": "https://regengine.vercel.app/tools/roi-calculator", "name": "Regulatory ROI Calculator" },
            { "@type": "ListItem", "position": 4, "url": "https://regengine.vercel.app/tools/exemption-qualifier", "name": "Exemption Qualifier" }
        ]
    }
};

export default function ToolsLandingPage() {
    return (
        <>
            <JSONLD data={jsonLd} />
            <ToolsLandingClient />
        </>
    );
}
