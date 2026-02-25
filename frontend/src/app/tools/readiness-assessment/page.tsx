import { Metadata } from "next";
import { ReadinessAssessmentClient } from "./components/ReadinessAssessmentClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "FSMA 204 Readiness Assessment | Free Compliance Score | RegEngine",
    description: "Score your facility's FSMA 204 compliance readiness in minutes. Covers product coverage, Critical Tracking Events, Key Data Elements, and system capabilities.",
    openGraph: {
        title: "FSMA 204 Readiness Assessment — RegEngine",
        description: "Free compliance readiness scoring for FSMA 204.",
        type: "website",
        url: "https://regengine.co/tools/readiness-assessment",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "FSMA 204 Readiness Assessment",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Score your facility's FSMA 204 compliance readiness across product coverage, CTEs, KDEs, and system capabilities.",
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

export default function ReadinessAssessmentPage() {
    return (
        <Suspense fallback={<div>Loading...</div>}>
            <JSONLD data={jsonLd} />
            <ReadinessAssessmentClient />
        </Suspense>
    );
}
