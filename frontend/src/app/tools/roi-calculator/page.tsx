import { Metadata } from "next";
import { ROICalculatorClient } from "./components/ROICalculatorClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
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
        <div className="min-h-screen py-10 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-base)]">
            <JSONLD data={jsonLd} />
            <div className="max-w-7xl mx-auto">
                <Breadcrumbs
                    items={[
                        { label: "Free Tools", href: "/tools" },
                        { label: "ROI Calculator" }
                    ]}
                />
                <ROICalculatorClient />
            </div>
        </div>
    );
}
