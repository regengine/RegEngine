import { permanentRedirect } from "next/navigation";

/**
 * Older index snippets still describe a case-studies URL. There is no named-
 * customer case study to restore, so send crawlers and humans to /proof, which
 * publishes inspectable sample exports instead of invented customer claims.
 */
export default function CaseStudiesRedirect() {
  permanentRedirect("/proof");
}
