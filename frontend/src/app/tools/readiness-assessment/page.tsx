import { Metadata } from "next";
import { ReadinessAssessmentClient } from "./components/ReadinessAssessmentClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";
import { Container } from "@/components/layout/container";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
    title: "FSMA 204 Readiness Self-Check | Free Gap Indicator | RegEngine",
    description: "Self-check your facility's FSMA 204 readiness across FTL product coverage, Critical Tracking Events, Key Data Elements, and system capabilities. Educational; not a compliance certification.",
    alternates: {
        canonical: "https://regengine.co/tools/readiness-assessment",
    },
    openGraph: {
        title: "FSMA 204 Readiness Self-Check — RegEngine",
        description: "Self-check your facility's FSMA 204 readiness across FTL coverage, CTEs, KDEs, and system capabilities. Free; educational only.",
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
    "description": "Self-check your facility's FSMA 204 readiness across product coverage, CTEs, KDEs, and system capabilities. Educational; not a compliance certification.",
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

const relatedTools = [
    { href: "/tools/drill-simulator", title: "24-Hour Drill Simulator", description: "Self-paced rehearsal for your §1.1455(c) records-on-request workflow." },
    { href: "/tools/recall-readiness", title: "FSMA 204 Readiness Self-Check", description: "Self-check your readiness for the §1.1455(c) records-on-request obligation." },
    { href: "/tools/sop-generator", title: "SOP Generator", description: "Auto-generate a starting-template FSMA 204 Traceability Plan — review with counsel before adoption." },
];

export default function ReadinessAssessmentPage() {
    return (
        <Suspense fallback={
            <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
                <Container width="tool">
                    <div className="border-b border-re-border-subtle pb-5">
                        <h1 className="text-title text-re-text-primary">FSMA 204 Readiness Self-Check</h1>
                        <p className="mt-1 max-w-[70ch] text-ui text-re-text-secondary">A self-paced readiness self-check based on your answers. Covers product coverage on the Food Traceability List, Critical Tracking Event mapping, Key Data Element completeness, and system integration. Educational; not an FDA audit, certification, or compliance determination.</p>
                    </div>
                    <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2">
                        {[
                            { title: "Product Coverage", body: "Do your products appear on the FDA Food Traceability List? Which categories apply?" },
                            { title: "CTE Readiness", body: "Can you capture records for all 7 Critical Tracking Events in your supply chain?" },
                            { title: "KDE Completeness", body: "Are you collecting the required Key Data Elements for each event type?" },
                            { title: "System Capabilities", body: "Can your current systems produce a sortable spreadsheet for an FDA records request within 24 hours (per §1.1455(c))?" },
                        ].map((tile) => (
                            <Card key={tile.title} variant="inset">
                                <CardContent className="p-4">
                                    <h3 className="text-subheading text-re-text-primary">{tile.title}</h3>
                                    <p className="mt-1 text-small text-re-text-tertiary">{tile.body}</p>
                                </CardContent>
                            </Card>
                        ))}
                    </div>
                    <div className="mt-6 space-y-3" role="status" aria-live="polite">
                        <Skeleton className="h-10 w-full" />
                        <Skeleton className="h-10 w-4/5" />
                        <p className="pt-2 text-small text-re-text-muted">Loading assessment…</p>
                    </div>
                </Container>
            </div>
        }>
            <JSONLD data={jsonLd} />
            <EmailGate toolName="readiness-assessment">
                <ReadinessAssessmentClient />
            </EmailGate>
            <RelatedTools tools={relatedTools} />
        </Suspense>
    );
}
