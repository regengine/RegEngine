import { Metadata } from "next";
import { ToolsLandingClient } from "./components/ToolsLandingClient";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "Free Strategic Compliance Tools | RegEngine",
    description: "Benchmark your readiness with free interactive tools. FTL checkers, AI model bias calculators, obligation scanners, and notice validators. Identify critical compliance gaps in minutes.",
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
    "name": "RegEngine Multi-Vertical Compliance Toolkit",
    "description": "A collection of free interactive tools for FSMA 204 and Financial Regulatory assessment.",
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    },
    "mainEntity": {
        "@type": "ItemList",
        "itemListElement": [
            { "@type": "ListItem", "position": 1, "url": "https://regengine.vercel.app/tools/ftl-checker", "name": "FTL Coverage Checker" },
            { "@type": "ListItem", "position": 2, "url": "https://regengine.vercel.app/tools/fsma-unified", "name": "Unified FSMA Dashboard" },
            { "@type": "ListItem", "position": 3, "url": "https://regengine.vercel.app/tools/bias-checker", "name": "AI Model Bias Checker" },
            { "@type": "ListItem", "position": 4, "url": "https://regengine.vercel.app/tools/obligation-scanner", "name": "Regulatory Obligation Scanner" },
            { "@type": "ListItem", "position": 5, "url": "https://regengine.vercel.app/tools/notice-validator", "name": "Adverse Action Notice Validator" },
            { "@type": "ListItem", "position": 6, "url": "https://regengine.vercel.app/tools/roi-calculator", "name": "Regulatory ROI Calculator" },
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
