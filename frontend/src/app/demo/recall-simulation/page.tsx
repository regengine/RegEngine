import { Metadata } from "next";

import RecallSimulationClient from "./RecallSimulationClient";

export const metadata: Metadata = {
  title: "Recall Simulation | FSMA 204 Traceability Demo | RegEngine",
  description:
    "Run realistic FSMA 204 recall scenarios and trace contamination impact across the supply chain in minutes.",
  openGraph: {
    title: "RegEngine Recall Simulation",
    description:
      "Simulate FDA recall response and compare baseline operations against RegEngine traceability infrastructure.",
    type: "website",
    url: "https://regengine.com/demo/recall-simulation",
  },
};

export default function RecallSimulationPage() {
  return <RecallSimulationClient />;
}
