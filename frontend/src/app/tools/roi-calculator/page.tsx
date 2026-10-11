import { Metadata } from "next";
import { ROICalculatorClient } from "./components/ROICalculatorClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";
import { Container } from "@/components/layout/container";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
    title: "FSMA 204 Savings Estimator | Illustrative ROI | RegEngine",
    description: "Estimate the rough savings opportunity from automating FSMA 204 compliance. Illustrative only — actual savings depend on your contracts, staffing, and existing systems.",
    alternates: {
        canonical: "https://regengine.co/tools/roi-calculator",
    },
    openGraph: {
        title: "FSMA 204 Savings Estimator — RegEngine",
        description: "Estimate the rough savings opportunity from automating FSMA 204 traceability. Illustrative only.",
        type: "website",
        url: "https://regengine.co/tools/roi-calculator",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "FSMA 204 Savings Estimator",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "financialVariable": "Compliance ROI",
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    }
};

function ROICalculatorFallback() {
    return (
        <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
            <Container width="tool">
                <div className="border-b border-re-border-subtle pb-5">
                    <h2 className="text-title text-re-text-primary">FSMA 204 Savings Estimator</h2>
                    <p className="mt-1 max-w-[70ch] text-ui text-re-text-secondary">Get a rough sense of where automation could pay back. Numbers are illustrative — actual savings depend on your contracts, staffing, and existing systems.</p>
                </div>
                <h2 className="mt-6 text-heading text-re-text-primary">What This Calculator Measures</h2>
                <div className="mt-4 grid grid-cols-1 gap-4 sm:grid-cols-2">
                    {[
                        { title: "Labor Cost Reduction", body: "Compare manual spreadsheet-based traceability against automated ingestion, validation, and export." },
                        { title: "Recall Risk Savings (illustrative)", body: "Rough sense of the cost difference between a §1.1455(c) 24-hour records response and a multi-day manual lookup. Not a forecast." },
                        { title: "Compliance Efficiency", body: "Measure time-to-export, KDE completeness rates, and CTE coverage across your supply chain." },
                        { title: "Retailer Readiness", body: "See how quickly you can prepare records to support major-retailer traceability programs. Specific retailer requirements vary by buyer." },
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
                    <p className="pt-2 text-small text-re-text-muted">Loading interactive calculator…</p>
                </div>
            </Container>
        </div>
    );
}

export default function ROICalculatorPage() {
    return (
        <>
            <Suspense fallback={<ROICalculatorFallback />}>
                <JSONLD data={jsonLd} />
                <EmailGate toolName="roi-calculator">
                    <ROICalculatorClient />
                </EmailGate>
            </Suspense>
            <RelatedTools tools={[
                { href: "/tools/self-reported-checklist", title: "Self Reported Checklist", description: "You answer and the page echoes what you reported. It does not score readiness." },
                { href: "/tools/sop-generator", title: "SOP Generator", description: "Auto-generate your FSMA 204 Traceability Plan and Standard Operating Procedures." },
                { href: "/tools/ftl-checker", title: "FTL Checker", description: "Confirm which products are covered by FSMA 204 before estimating compliance costs." },
            ]} />
        </>
    );
}
