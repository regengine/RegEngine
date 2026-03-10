import { permanentRedirect } from "next/navigation";

export default function AnomalySimulatorRedirectPage() {
  permanentRedirect("/tools/drill-simulator");
}
