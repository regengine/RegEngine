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
        url: "https://regengine.vercel.app/tools/roi-calculator",
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
        <div className="min-h-screen bg-[var(--re-surface-base)] flex flex-col items-center justify-center gap-6 px-6 text-center">
            <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
                <svg className="w-8 h-8 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path d="M12 2v20M17 5H9.5a3.5 3.5 0 0 0 0 7h5a3.5 3.5 0 0 1 0 7H6" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round"/></svg>
            </div>
            <div>
                <h1 className="text-xl font-bold text-[var(--re-text-primary)] mb-2">FSMA 204 ROI Calculator</h1>
                <p className="text-sm text-[var(--re-text-muted)] max-w-sm">Estimate your labor savings, recall cost reduction, and compliance efficiency gains from automating FSMA 204 traceability with RegEngine.</p>
            </div>
            <div className="flex gap-2 items-center text-xs text-[var(--re-text-disabled)]">
                <div className="w-3 h-3 rounded-full border-2 border-emerald-400 border-t-transparent animate-spin" />
                Loading calculator…
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
