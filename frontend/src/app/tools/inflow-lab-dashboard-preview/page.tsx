import { Metadata } from "next";

import { DashboardInflowLab } from "@/app/tools/inflow-lab/components/DashboardInflowLab";

export const metadata: Metadata = {
    title: "Inflow Lab Dashboard Preview | RegEngine",
    description:
        "Public preview of the dashboard-style Inflow Lab proof experience for reviewing realistic supplier traceability flows.",
};

export default function InflowLabDashboardPreviewPage() {
    return <DashboardInflowLab previewMode />;
}
