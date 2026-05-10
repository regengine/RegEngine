import { Metadata } from "next";
import { Suspense } from "react";
import { CTEMapperClient } from "./components/CTEMapperClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";
import { EmailGate } from "@/components/tools/EmailGate";
import { RelatedTools } from "@/components/tools/RelatedTools";

export const metadata: Metadata = {
    title: "CTE Mapper | FSMA 204 Critical Tracking Events by Role | RegEngine",
    description: "See which Critical Tracking Events typically apply to your role under 21 CFR Part 1 Subpart S. Educational starting reference; §1.1305 exemptions may change which CTEs apply to your specific operation.",
    alternates: {
        canonical: "https://regengine.co/tools/cte-mapper",
    },
    openGraph: {
        title: "CTE Mapper — RegEngine",
        description: "See which Critical Tracking Events typically apply to your role under FSMA 204. Educational starting reference; not a regulatory determination.",
        type: "website",
        url: "https://regengine.co/tools/cte-mapper",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "CTE Coverage Mapper",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Educational reference mapping common supply-chain roles to FSMA 204 Critical Tracking Events. Not a regulatory determination.",
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

function CTEMapperFallback() {
    return (
        <div className="px-6 py-16">
            <div className="max-w-2xl mx-auto text-center mb-12">
                <div className="w-16 h-16 rounded-2xl bg-re-brand-muted border border-re-brand/20 flex items-center justify-center mx-auto mb-6">
                    <svg className="w-8 h-8 text-re-brand" fill="none" viewBox="0 0 24 24" stroke="currentColor"><rect x="3" y="3" width="7" height="7" rx="1" strokeWidth="1.5"/><rect x="14" y="3" width="7" height="7" rx="1" strokeWidth="1.5"/><rect x="3" y="14" width="7" height="7" rx="1" strokeWidth="1.5"/><path d="M17.5 17.5h.01M14 17.5h3.5m0 0V14" strokeWidth="1.5" strokeLinecap="round"/></svg>
                </div>
                <h1 className="text-2xl font-bold text-[var(--re-text-primary)] mb-3">CTE Coverage Mapper</h1>
                <p className="text-sm text-[var(--re-text-muted)] max-w-lg mx-auto leading-relaxed">See which Critical Tracking Events typically apply to your role under 21 CFR Part 1 Subpart S. Educational starting reference; §1.1305 exemptions may change which CTEs apply to your specific operation.</p>
            </div>
            <div className="max-w-2xl mx-auto">
                <h2 className="text-lg font-semibold text-[var(--re-text-primary)] mb-4">FSMA 204 Critical Tracking Events</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-8">
                    {[
                        { cte: "Harvesting (§1.1325)", desc: "When a food is picked, collected, or gathered from a growing area." },
                        { cte: "Cooling (§1.1325)", desc: "Active temperature reduction after harvest. §1.1325 covers Harvesting and Cooling in a single section." },
                        { cte: "Initial Packing (§1.1330)", desc: "First time a raw agricultural commodity (other than food obtained from a fishing vessel) is packed." },
                        { cte: "First Land-Based Receiving (§1.1335)", desc: "First land-based receipt of food obtained from a fishing vessel. Applies only to food obtained from a fishing vessel — non-seafood importers perform §1.1345 Receiving, not FLBR." },
                        { cte: "Shipping (§1.1340)", desc: "Every time the food leaves a facility in the supply chain." },
                        { cte: "Receiving (§1.1345)", desc: "Every time the food arrives at a new facility. Subject to the §1.1305(j) exemption for restaurants and retail food establishments selling directly to consumers." },
                        { cte: "Transformation (§1.1350)", desc: "Manufacturing, processing, or significant alteration that produces a new traceability lot." },
                    ].map((item) => (
                        <div key={item.cte} className="rounded-lg border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] p-3">
                            <span className="text-sm font-semibold text-re-brand">{item.cte}</span>
                            <p className="text-xs text-[var(--re-text-muted)] mt-1">{item.desc}</p>
                        </div>
                    ))}
                </div>
                <div className="flex gap-2 items-center justify-center text-xs text-[var(--re-text-disabled)]">
                    <div className="w-3 h-3 rounded-full border-2 border-re-brand border-t-transparent animate-spin" />
                    Loading interactive mapper…
                </div>
            </div>
        </div>
    );
}

export default function CTEMapperPage() {
    return (
        <>
            <div className="min-h-screen py-10 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-base)]">
                <JSONLD data={jsonLd} />
                <div className="max-w-7xl mx-auto">
                    <Breadcrumbs
                        items={[
                            { label: "Free Tools", href: "/tools" },
                            { label: "CTE Coverage Mapper" }
                        ]}
                    />
                    <Suspense fallback={<CTEMapperFallback />}>
                        <EmailGate toolName="cte-mapper">
                            <CTEMapperClient />
                        </EmailGate>
                    </Suspense>
                </div>
            </div>
            <RelatedTools tools={[
                { href: "/tools/kde-checker", title: "KDE Checker", description: "Generate a customized Key Data Element checklist for each CTE and FTL product type." },
                { href: "/tools/ftl-checker", title: "FTL Checker", description: "Verify which of your food products are covered by FDA FSMA 204 requirements." },
                { href: "/tools/drill-simulator", title: "24-Hour Drill Simulator", description: "Self-paced rehearsal for your §1.1455(c) records-on-request workflow." },
            ]} />
        </>
    );
}
