import { Metadata } from "next";

import { DashboardInflowLab } from "@/app/tools/inflow-lab/components/DashboardInflowLab";
import { FeatureNotEnabled } from "@/components/experimental/FeatureNotEnabled";
import { isExperimentalToolEnabled } from "@/lib/experimental-features";

export const metadata: Metadata = {
    title: "Inflow Lab Dashboard Preview | RegEngine",
    description:
        "Public preview of the dashboard-style Inflow Lab proof experience for reviewing realistic supplier traceability flows.",
};

export default function InflowLabDashboardPreviewPage() {
    if (!isExperimentalToolEnabled("inflow-lab-dashboard-preview")) {
        return (
            <FeatureNotEnabled
                featureName="Inflow Lab Dashboard Preview"
                backHref="/tools"
                backLabel="Back to free tools"
            />
        );
    }
    return <DashboardInflowLab previewMode />;
}
