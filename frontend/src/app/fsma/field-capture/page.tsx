import { permanentRedirect } from "next/navigation";

export default function FieldCaptureLegacyRoute() {
  permanentRedirect("/mobile/capture");
}
