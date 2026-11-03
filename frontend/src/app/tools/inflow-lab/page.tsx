import { Metadata } from "next";
import { InflowLabClient } from "./components/InflowLabClient";
import { FeatureNotEnabled } from "@/components/experimental/FeatureNotEnabled";
import {
    experimentalFeaturesEnabled,
    isExperimentalToolEnabled,
} from "@/lib/experimental-features";

export const metadata: Metadata = {
    title: "RegEngine Inflow Lab | Supplier Data Preflight Workbench",
    description:
        "Preflight supplier traceability data, validate FSMA 204 Critical Tracking Event (CTE) and Key Data Element (KDE) coverage, generate fix queues, replay scenarios, and gate production evidence commits.",
    openGraph: {
        title: "RegEngine Inflow Lab | Supplier Data Preflight Workbench",
        description: "Inflow prepares supplier data before the Engine commits validated, tenant-scoped FSMA 204 evidence.",
        type: "website",
        url: "https://www.regengine.co/tools/inflow-lab",
    },
};

export default function InflowLabPage() {
    if (!isExperimentalToolEnabled("inflow-lab")) {
        return (
            <FeatureNotEnabled
                featureName="Inflow Lab"
                backHref="/tools"
                backLabel="Back to free tools"
            />
        );
    }
    // Simulator/demo path works with the per-tool flag alone. CSV evaluate hits
    // the experimental sandbox router, so keep that control off unless the
    // broader experimental surface (and matching backend routers) is enabled.
    return <InflowLabClient csvEvaluateEnabled={experimentalFeaturesEnabled()} />;
}
