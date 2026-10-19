import { Metadata } from "next";
import { Suspense } from "react";
import { CTEMapperClient } from "./components/CTEMapperClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { Container } from "@/components/layout/container";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";
import { Card } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";

export const metadata: Metadata = {
    title: "FSMA 204 CTE Mapper by Role | RegEngine",
    description: "See which Critical Tracking Event (CTE) types usually apply to a role under 21 CFR Part 1 Subpart S. Educational only. Exemptions can change what applies.",
    alternates: {
        canonical: "https://regengine.co/tools/cte-mapper",
    },
    openGraph: {
        title: "FSMA 204 CTE Mapper by Role | RegEngine",
        description: "See which Critical Tracking Event (CTE) types usually apply to a role under 21 CFR Part 1 Subpart S. Educational only. Exemptions can change what applies.",
        type: "website",
        url: "https://regengine.co/tools/cte-mapper",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "CTE Mapper",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Educational reference mapping common supply-chain roles to FSMA 204 Critical Tracking Event (CTE) types. Not a regulatory determination.",
    "publisher": {
        "@type": "Organization",
        "name": "RegEngine"
    }
};

function CTEMapperFallback() {
    return (
        <div className="py-6" aria-busy="true">
            <div className="mb-10 text-center">
                <p className="text-title text-re-text-primary">CTE Mapper</p>
                <p className="mx-auto mt-3 max-w-[70ch] text-ui text-re-text-secondary">See which Critical Tracking Event (CTE) types typically apply to your role under 21 CFR Part 1 Subpart S. Educational starting reference; §1.1305 exemptions may change which CTEs apply to your specific operation.</p>
            </div>
            <div className="mx-auto max-w-2xl">
                <h2 className="mb-4 text-heading text-re-text-primary">FSMA 204 Critical Tracking Events</h2>
                <div className="mb-8 grid grid-cols-1 gap-3 sm:grid-cols-2">
                    {[
                        { cte: "Harvesting (§1.1325)", desc: "When a food is picked, collected, or gathered from a growing area." },
                        { cte: "Cooling (§1.1325)", desc: "Active temperature reduction after harvest. §1.1325 covers Harvesting and Cooling in a single section." },
                        { cte: "Initial Packing (§1.1330)", desc: "First time a raw agricultural commodity (other than food obtained from a fishing vessel) is packed." },
                        { cte: "First Land-Based Receiving (§1.1335)", desc: "First land-based receipt of food obtained from a fishing vessel. Applies only to food obtained from a fishing vessel. Non-seafood importers perform §1.1345 Receiving, not FLBR." },
                        { cte: "Shipping (§1.1340)", desc: "Every time the food leaves a facility in the supply chain." },
                        { cte: "Receiving (§1.1345)", desc: "Every time the food arrives at a new facility. Subject to the §1.1305(j) exemption for restaurants and retail food establishments selling directly to consumers." },
                        { cte: "Transformation (§1.1350)", desc: "Manufacturing, processing, or significant alteration that produces a new traceability lot." },
                    ].map((item) => (
                        <Card key={item.cte} variant="inset" padding="compact">
                            <span className="text-subheading text-re-text-primary">{item.cte}</span>
                            <p className="mt-1 text-small text-re-text-tertiary">{item.desc}</p>
                        </Card>
                    ))}
                </div>
                <Skeleton className="mb-4 h-48 w-full rounded-lg" />
                <p className="text-center text-small text-re-text-muted">
                    Loading interactive mapper…
                </p>
            </div>
        </div>
    );
}

export default function CTEMapperPage() {
    return (
        <>
            <div className="min-h-screen bg-re-surface-base py-6 sm:py-8">
                <JSONLD data={jsonLd} />
                <Container width="tool">
                    <Breadcrumbs
                        items={[
                            { label: "Free Tools", href: "/tools" },
                            { label: "CTE Mapper" }
                        ]}
                    />
                    <Suspense fallback={<CTEMapperFallback />}>
                        <EmailGate toolName="cte-mapper">
                            <CTEMapperClient />
                        </EmailGate>
                    </Suspense>
                </Container>
            </div>
            <RelatedTools tools={[
                { href: "/tools/kde-checker", title: "KDE Field Checklist", description: "Generate a customized Key Data Element (KDE) checklist for each CTE and FTL product type." },
                { href: "/tools/ftl-checker", title: "FTL Checker", description: "Verify which of your food products are covered by FDA FSMA 204 requirements." },
                { href: "/tools/drill-simulator", title: "24 Hour Drill Simulator", description: "Self-paced rehearsal for your §1.1455(c) records-on-request workflow." },
            ]} />
        </>
    );
}
