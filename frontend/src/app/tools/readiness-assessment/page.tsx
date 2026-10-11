import type { Metadata } from "next";
import { redirect } from "next/navigation";

/**
 * Old URL. The checklist does not score readiness, so this path only
 * redirects. next.config.js also redirects it. This page redirect covers
 * a host that does not apply that config, and it does not render the
 * old assessment (a render failure here was a candidate for HTTP 500).
 */
export const metadata: Metadata = {
    title: "Self Reported Checklist | FSMA 204 | RegEngine",
    description:
        "You answer and the page echoes what you reported. It does not verify records, score readiness, or decide if you can meet the records request rule.",
    robots: { index: false, follow: true },
    alternates: {
        canonical: "https://regengine.co/tools/self-reported-checklist",
    },
    openGraph: {
        title: "Self Reported Checklist | FSMA 204 | RegEngine",
        description:
            "You answer and the page echoes what you reported. It does not verify records, score readiness, or decide if you can meet the records request rule.",
        type: "website",
        url: "https://regengine.co/tools/self-reported-checklist",
    },
};

export default function ReadinessAssessmentPage() {
    redirect("/tools/self-reported-checklist");
}
