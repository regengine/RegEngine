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
        <Suspense fallback={
            <div className="min-h-screen bg-[var(--re-surface-base)] px-6 py-16">
                <div className="max-w-2xl mx-auto text-center">
                    <h1 className="text-2xl font-bold text-[var(--re-text-primary)] mb-3">FSMA 204 Readiness Assessment</h1>
                    <p className="text-sm text-[var(--re-text-muted)] max-w-lg mx-auto mb-8 leading-relaxed">Score your facility&apos;s FSMA 204 compliance readiness in minutes. This assessment covers product coverage on the Food Traceability List, Critical Tracking Event mapping, Key Data Element completeness, and system integration capabilities.</p>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-left mb-8">
                        <div className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] p-4">
                            <h3 className="text-sm font-semibold text-emerald-400 mb-1">Product Coverage</h3>
                            <p className="text-xs text-[var(--re-text-muted)]">Do your products appear on the FDA Food Traceability List? Which categories apply?</p>
                        </div>
                        <div className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] p-4">
                            <h3 className="text-sm font-semibold text-emerald-400 mb-1">CTE Readiness</h3>
                            <p className="text-xs text-[var(--re-text-muted)]">Can you capture records for all 7 Critical Tracking Events in your supply chain?</p>
                        </div>
                        <div className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] p-4">
                            <h3 className="text-sm font-semibold text-emerald-400 mb-1">KDE Completeness</h3>
                            <p className="text-xs text-[var(--re-text-muted)]">Are you collecting the required Key Data Elements for each event type?</p>
                        </div>
                        <div className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] p-4">
                            <h3 className="text-sm font-semibold text-emerald-400 mb-1">System Capabilities</h3>
                            <p className="text-xs text-[var(--re-text-muted)]">Can your current systems produce FDA-ready exports within 24 hours of a records request?</p>
                        </div>
                    </div>
                    <div className="flex gap-2 items-center justify-center text-xs text-[var(--re-text-disabled)]">
                        <div className="w-3 h-3 rounded-full border-2 border-emerald-400 border-t-transparent animate-spin" />
                        Loading assessment…
                    </div>
                </div>
            </div>
        }>
            <JSONLD data={jsonLd} />
            <ReadinessAssessmentClient />
        </Suspense>
    );
}
