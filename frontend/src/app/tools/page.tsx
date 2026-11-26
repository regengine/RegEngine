import { Metadata } from "next";
import { isExperimentalToolHrefHidden } from "@/lib/experimental-features";
import { ToolsLandingClient } from "./components/ToolsLandingClient";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "Free FSMA 204 Tools | RegEngine",
    description: "Free FTL, CTE, KDE, and TLC tools. FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive.",
    openGraph: {
        title: "Free FSMA 204 Tools | RegEngine",
        description: "Free FTL, CTE, KDE, and TLC tools. FDA has said it will not enforce the Food Traceability Rule before July 20, 2028, following a Congressional directive.",
        type: "website",
        url: "https://regengine.co/tools",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "CollectionPage",
    "name": "RegEngine Tools",
    "description": "Small tools for list checks and field checks. Educational. Not an FDA determination.",
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    },
    "mainEntity": {
        "@type": "ItemList",
        "itemListElement": [
            { "url": "https://regengine.co/tools/ftl-checker", "name": "FTL List Checker" },
            { "url": "https://regengine.co/tools/cte-mapper", "name": "CTE Mapper" },
            { "url": "https://regengine.co/tools/kde-checker", "name": "KDE Field Checklist" },
            { "url": "https://regengine.co/tools/tlc-validator", "name": "TLC Format Check" },
            { "url": "https://regengine.co/tools/self-reported-checklist", "name": "Self Reported Checklist" },
            { "url": "https://regengine.co/tools/records-request-checklist", "name": "Records Request Checklist" },
        ]
            .filter((item) => !isExperimentalToolHrefHidden(item.url.replace("https://regengine.co", "")))
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
