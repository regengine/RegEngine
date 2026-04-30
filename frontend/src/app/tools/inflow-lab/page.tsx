import { Metadata } from "next";
import { InflowLabClient } from "./components/InflowLabClient";

export const metadata: Metadata = {
    title: "RegEngine Inflow Lab | Sandbox and Mock Feed Boundary",
    description:
        "Diagnose sandbox CSV data, run mock FSMA 204 feed checks, and keep production evidence limited to authenticated persisted records.",
    openGraph: {
        title: "RegEngine Inflow Lab",
        description: "Operational boundary for sandbox diagnosis, mock feed validation, authenticated feed monitoring, and evidence handoff.",
        type: "website",
        url: "https://www.regengine.co/tools/inflow-lab",
    },
};

export default function InflowLabPage() {
    return <InflowLabClient />;
}
