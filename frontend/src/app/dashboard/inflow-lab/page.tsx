import { Metadata } from "next";
import { DashboardInflowLab } from "@/app/tools/inflow-lab/components/DashboardInflowLab";

export const metadata: Metadata = {
    title: "Inflow Lab | RegEngine Dashboard",
    description:
        "Test supplier traceability data before it flows into production exports — sandbox-only diagnostics, grouped exceptions, and a sticky lot lifecycle.",
};

export default function DashboardInflowLabPage() {
    return <DashboardInflowLab />;
}
