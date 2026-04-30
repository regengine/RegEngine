import { Metadata } from "next";
import { InflowLabClient } from "./components/InflowLabClient";

export const metadata: Metadata = {
    title: "RegEngine Inflow Lab | Mock FSMA 204 Pipeline",
    description:
        "Run a mock FSMA 204 inflow pipeline across fixture loading, CTE generation, delivery, lot tracing, and FDA-ready export checks.",
    openGraph: {
        title: "RegEngine Inflow Lab",
        description: "Mock-first FSMA 204 traceability pipeline simulator.",
        type: "website",
        url: "https://www.regengine.co/tools/inflow-lab",
    },
};

export default function InflowLabPage() {
    return <InflowLabClient />;
}
