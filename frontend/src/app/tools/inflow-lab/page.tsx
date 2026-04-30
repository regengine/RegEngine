import { Metadata } from "next";
import { InflowLabClient } from "./components/InflowLabClient";

export const metadata: Metadata = {
    title: "RegEngine Inflow Lab | Supplier Data Preflight Workbench",
    description:
        "Preflight supplier traceability data, validate FSMA 204 CTE/KDE coverage, generate fix queues, replay scenarios, and gate production evidence commits.",
    openGraph: {
        title: "RegEngine Inflow Lab | Supplier Data Preflight Workbench",
        description: "Inflow prepares supplier data before the Engine commits validated, tenant-scoped FSMA 204 evidence.",
        type: "website",
        url: "https://www.regengine.co/tools/inflow-lab",
    },
};

export default function InflowLabPage() {
    return <InflowLabClient />;
}
