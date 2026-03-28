import { Metadata } from "next";
import { ROICalculatorClient } from "./components/ROICalculatorClient";
import { Suspense } from "react";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "Regulatory ROI Calculator | FSMA 204 Automation Savings | RegEngine",
    description: "Quantify the financial impact of manual compliance vs. the RegEngine platform with our personalized ROI engine. Calculate labor savings and risk reduction.",
    openGraph: {
        title: "Regulatory ROI Calculator — RegEngine",
        description: "Calculate your FSMA 204 automation savings.",
        type: "website",
        url: "https://www.regengine.co/tools/roi-calculator",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "Regulatory ROI Calculator",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "financialVariable": "Compliance ROI",
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

function ROICalculatorFallback() {
    return (
        <div className="min-h-screen bg-[var(--re-surface-base)] px-6 py-16">
            <div className="max-w-2xl mx-auto text-center mb-12">
                <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center mx-auto mb-6">
                    <svg className="w-8 h-8 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
                </div>
                <h1 className="text-2xl font-bold text-[var(--re-text-primary)] mb-3">FSMA 204 ROI Calculator</h1>
                <p className="text-sm text-[var(--re-text-muted)] max-w-lg mx-auto leading-relaxed">Estimate your labor savings, recall cost reduction, and compliance efficiency gains from automating FSMA 204 traceability with RegEngine. Enter your facility count, product volume, and current compliance spend to see personalized results.</p>
            </div>
            <div className="max-w-2xl mx-auto">
                <h2 className="text-lg font-semibold text-[var(--re-text-primary)] mb-4">What This Calculator Measures</h2>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
                    <div className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] p-4">
                        <h3 className="text-sm font-semibold text-emerald-400 mb-1">Labor Cost Reduction</h3>
                        <p className="text-xs text-[var(--re-text-muted)]">Compare manual spreadsheet-based traceability against automated ingestion, validation, and export.</p>
                    </div>
                    <div className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] p-4">
                        <h3 className="text-sm font-semibold text-emerald-400 mb-1">Recall Risk Savings</h3>
                        <p className="text-xs text-[var(--re-text-muted)]">Estimate the cost difference between a 24-hour FDA response with cryptographic records vs. multi-day manual lookup.</p>
                    </div>
                    <div className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] p-4">
                        <h3 className="text-sm font-semibold text-emerald-400 mb-1">Compliance Efficiency</h3>
                        <p className="text-xs text-[var(--re-text-muted)]">Measure time-to-export, KDE completeness rates, and CTE coverage across your supply chain.</p>
                    </div>
                    <div className="rounded-xl border border-[rgba(255,255,255,0.06)] bg-[rgba(255,255,255,0.02)] p-4">
                        <h3 className="text-sm font-semibold text-emerald-400 mb-1">Retailer Readiness</h3>
                        <p className="text-xs text-[var(--re-text-muted)]">See how quickly you can meet Walmart, Kroger, and Costco traceability requirements with automated evidence generation.</p>
                    </div>
                </div>
                <div className="flex gap-2 items-center justify-center text-xs text-[var(--re-text-disabled)]">
                    <div className="w-3 h-3 rounded-full border-2 border-emerald-400 border-t-transparent animate-spin" />
                    Loading interactive calculator…
                </div>
            </div>
        </div>
    );
}

export default function ROICalculatorPage() {
    return (
        <Suspense fallback={<ROICalculatorFallback />}>
            <JSONLD data={jsonLd} />
            <ROICalculatorClient />
        </Suspense>
    );
}
