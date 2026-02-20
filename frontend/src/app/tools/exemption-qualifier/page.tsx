import { Metadata } from "next";
import { ExemptionQualifierClient } from "./components/ExemptionQualifierClient";
import { Breadcrumbs } from "@/components/layout/breadcrumbs";
import { JSONLD } from "@/components/seo/json-ld";

export const metadata: Metadata = {
    title: "FSMA 204 Exemption Qualifier | Compliance Eligibility Checker | RegEngine",
    description: "Quickly determine your FSMA 204 compliance status and eligibility for small business or other exemptions. Detailed 21 CFR Subpart S analysis.",
    openGraph: {
        title: "FSMA 204 Exemption Qualifier — RegEngine",
        description: "Check your FSMA 204 exemption eligibility.",
        type: "website",
        url: "https://regengine.vercel.app/tools/exemption-qualifier",
    },
};

const jsonLd = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "FSMA 204 Exemption Qualifier",
    "operatingSystem": "All",
    "applicationCategory": "BusinessApplication",
    "description": "Determine eligibility for FSMA 204 small business and role-based exemptions.",
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

export default function ExemptionQualifierPage() {
    return (
        <div className="min-h-screen py-10 px-4 sm:px-6 lg:px-8 bg-[var(--re-surface-base)]">
            <JSONLD data={jsonLd} />
            <div className="max-w-7xl mx-auto">
                <Breadcrumbs
                    items={[
                        { label: "Free Tools", href: "/tools" },
                        { label: "Exemption Qualifier" }
                    ]}
                />
                <ExemptionQualifierClient />
            </div>
        </div>
    );
}
