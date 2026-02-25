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

export default function ROICalculatorPage() {
    return (
        <Suspense fallback={<div>Loading...</div>}>
            <JSONLD data={jsonLd} />
            <ROICalculatorClient />
        </Suspense>
    );
}
