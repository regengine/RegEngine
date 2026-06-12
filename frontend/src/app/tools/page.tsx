import { Metadata } from "next";
import { experimentalFeaturesEnabled, isExperimentalToolHref } from "@/lib/experimental-features";
import { ToolsLandingClient } from "./components/ToolsLandingClient";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "Free Strategic Compliance Tools | RegEngine",
    description: "Free FSMA 204 compliance tools including FTL checker, CTE/KDE validators, readiness assessments, and traceability workflow utilities.",
    openGraph: {
        title: "FSMA 204 Free Tools — RegEngine",
        description: "Free FSMA 204 compliance tools for traceability readiness.",
        type: "website",
        url: "https://regengine.co/tools",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    "name": "RegEngine FSMA 204 Compliance Toolkit",
    "description": "A collection of free interactive tools for FSMA 204 food traceability compliance.",
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    },
    "mainEntity": {
        "@type": "ItemList",
        "itemListElement": [
            { "url": "https://regengine.co/tools/ftl-checker", "name": "FTL Coverage Checker" },
            { "url": "https://regengine.co/tools/fsma-unified", "name": "Cold Chain Anomaly Detector" },
            { "url": "https://regengine.co/tools/kde-checker", "name": "KDE Completeness Checker" },
            { "url": "https://regengine.co/tools/cte-mapper", "name": "CTE Coverage Mapper" },
            { "url": "https://regengine.co/tools/recall-readiness", "name": "FSMA 204 Readiness Self-Check" },
            { "url": "https://regengine.co/tools/roi-calculator", "name": "FSMA 204 Savings Estimator" },
            { "url": "https://regengine.co/tools/inflow-lab", "name": "Inflow Lab" },
        ]
            .filter((item) => experimentalFeaturesEnabled() || !isExperimentalToolHref(item.url.replace("https://regengine.co", "")))
            .map((item, index) => ({ "@type": "ListItem", "position": index + 1, ...item }))
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
