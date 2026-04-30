import { Metadata } from "next";
import { InflowLabClient } from "@/app/tools/inflow-lab/components/InflowLabClient";

export const metadata: Metadata = {
    title: "Inflow Lab | RegEngine Dashboard",
    description:
        "Separate sandbox diagnosis, mock feed validation, authenticated feed monitoring, and production evidence from the RegEngine command center.",
};

export default function DashboardInflowLabPage() {
    return <InflowLabClient mode="dashboard" />;
}
