import { Metadata } from "next";
import { ToolsLandingClient } from "./components/ToolsLandingClient";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "Free Strategic Compliance Tools | RegEngine",
    description: "Free FSMA 204 compliance tools including FTL checker, CTE/KDE validators, readiness assessments, and traceability workflow utilities.",
    openGraph: {
        title: "FSMA 204 Free Tools — RegEngine",
        description: "Free FSMA 204 compliance tools for traceability readiness.",
        type: "website",
        url: "https://www.regengine.co/tools",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    "name": "RegEngine Multi-Vertical Compliance Toolkit",
    "description": "A collection of free interactive tools for FSMA 204 food traceability compliance.",
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    },
    "mainEntity": {
        "@type": "ItemList",
        "itemListElement": [
            { "@type": "ListItem", "position": 1, "url": "https://www.regengine.co/tools/ftl-checker", "name": "FTL Coverage Checker" },
            { "@type": "ListItem", "position": 2, "url": "https://www.regengine.co/tools/fsma-unified", "name": "Unified FSMA Dashboard" },
            { "@type": "ListItem", "position": 3, "url": "https://www.regengine.co/tools/kde-checker", "name": "KDE Completeness Checker" },
            { "@type": "ListItem", "position": 4, "url": "https://www.regengine.co/tools/cte-mapper", "name": "CTE Coverage Mapper" },
            { "@type": "ListItem", "position": 5, "url": "https://www.regengine.co/tools/recall-readiness", "name": "Recall Readiness Score" },
            { "@type": "ListItem", "position": 6, "url": "https://www.regengine.co/tools/roi-calculator", "name": "Regulatory ROI Calculator" },
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
