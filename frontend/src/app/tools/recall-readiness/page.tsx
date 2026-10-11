import type { Metadata } from "next";
import { redirect } from "next/navigation";

/**
 * Old URL. The records checklist is not a recall readiness score, so this
 * path only redirects. next.config.js also redirects it. This page redirect
 * covers a host that does not apply that config, and it does not render the
 * old self-check.
 */
export const metadata: Metadata = {
    title: "FSMA 204 Records Request Checklist | RegEngine",
    description:
        "A self reported checklist for an FDA records request under 21 CFR 1.1455. Not a 24 hour test, not a readiness score, and not legal advice.",
    robots: { index: false, follow: true },
    alternates: {
        canonical: "https://regengine.co/tools/records-request-checklist",
    },
    openGraph: {
        title: "FSMA 204 Records Request Checklist | RegEngine",
        description:
            "A self reported checklist for an FDA records request under 21 CFR 1.1455. Not a 24 hour test, not a readiness score, and not legal advice.",
        type: "website",
        url: "https://regengine.co/tools/records-request-checklist",
    },
};

export default function RecallReadinessPage() {
    redirect("/tools/records-request-checklist");
}
