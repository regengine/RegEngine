import { Metadata } from "next";
import { InflowLabClient } from "@/app/tools/inflow-lab/components/InflowLabClient";

export const metadata: Metadata = {
    title: "Inflow Lab | RegEngine Dashboard",
    description:
        "Simulate inbound FSMA 204 traceability records, validate delivery, trace lots, and prepare evidence exports from the RegEngine command center.",
};

export default function DashboardInflowLabPage() {
    return <InflowLabClient mode="dashboard" />;
}
