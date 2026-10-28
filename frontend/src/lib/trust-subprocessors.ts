export type SubprocessorAvailability =
  | 'default'
  | 'where_configured'
  | 'not_in_production';

export interface TrustSubprocessor {
  name: string;
  purpose: string;
  dataProcessed: string;
  location: string;
  /** Processing region stated on the vendor's official DPA or regions page. Empty when unstated. */
  region: string;
  /** Cross-border transfer mechanism stated on the vendor's official DPA. Empty when unstated. */
  transferMechanism: string;
  link: string;
  availability: SubprocessorAvailability;
  availabilityLabel: string;
}

/**
 * Public Trust / DPA subprocessor inventory.
 * In production use: Supabase, Railway, Vercel, Sentry, Stripe, PostHog, Resend, TypeSafe AI, Cloudflare R2.
 * Not enabled in production as of Oct 28, 2026: OpenAI, Google Cloud Vertex AI, LlamaCloud.
 * region and transferMechanism are filled only from each vendor's official DPA / regions pages.
 */
export const TRUST_SUBPROCESSORS: TrustSubprocessor[] = [
  {
    name: 'Supabase',
    purpose:
      'Authentication for developer-portal accounts and a legacy session-validation path; stores developer-portal API-key records and pre-sales assessment leads. Core tenant workspace data is stored in PostgreSQL managed by Railway.',
    dataProcessed:
      'Developer-portal account records, API-key records, pre-sales assessment leads, and authentication metadata.',
    location: 'United States; project region per executed agreement/current DPA',
    region: 'Customer directed project region',
    transferMechanism:
      'EU Standard Contractual Clauses (Module 2 and Module 3); UK International Data Transfer Addendum; Swiss Addendum',
    link: 'https://supabase.com/privacy',
    availability: 'default',
    availabilityLabel: 'Default platform processor',
  },
  {
    name: 'Railway',
    purpose:
      'Platform hosting the RegEngine application and the core PostgreSQL database for tenant workspace data.',
    dataProcessed:
      'Workspace records, evidence ledger rows, API requests, application logs, and workflow metadata.',
    location: 'United States',
    region: 'United States',
    transferMechanism:
      'EU U.S. Data Privacy Framework and/or EU Standard Contractual Clauses with UK International Data Transfer Addendum',
    link: 'https://railway.app/legal/privacy',
    availability: 'default',
    availabilityLabel: 'Default platform processor',
  },
  {
    name: 'Vercel',
    purpose: 'Frontend hosting, edge delivery, and authenticated request routing.',
    dataProcessed: 'Authenticated web requests, CDN metadata, and limited edge logs.',
    location: 'United States / global CDN',
    region: 'United States',
    transferMechanism:
      'EU Standard Contractual Clauses with UK International Data Transfer Agreement',
    link: 'https://vercel.com/legal/privacy-policy',
    availability: 'default',
    availabilityLabel: 'Default platform processor',
  },
  {
    name: 'Sentry',
    purpose:
      'Server, edge, and backend error monitoring with PII scrubbing configured where available.',
    dataProcessed:
      'Error events, stack traces, request metadata, and environment diagnostics. Browser replay capture is not enabled by default.',
    location: 'United States',
    region: 'United States and other countries where Sentry or its subprocessors maintain operations',
    transferMechanism:
      'EU U.S. Data Privacy Framework; EU Standard Contractual Clauses with UK International Data Transfer Addendum and Swiss adaptations',
    link: 'https://sentry.io/privacy/',
    availability: 'where_configured',
    availabilityLabel: 'Where configured',
  },
  {
    name: 'Stripe',
    purpose: 'Billing, invoices, payment processing, and tax support.',
    dataProcessed:
      'Billing contact information, subscription metadata, payment processor tokens, and invoice history.',
    location: 'United States',
    region: 'United States',
    transferMechanism:
      'EU U.S. Data Privacy Framework; EEA Standard Contractual Clauses; UK International Data Transfer Addendum',
    link: 'https://stripe.com/privacy',
    availability: 'where_configured',
    availabilityLabel: 'Where billing is enabled',
  },
  {
    name: 'PostHog',
    purpose: 'Privacy-conscious product analytics after consent or workspace enablement.',
    dataProcessed:
      'Workspace-scoped product events, pseudonymous identifiers, and consent metadata.',
    location: 'United States',
    region: 'Customer selected data center location',
    transferMechanism:
      'EU U.S. Data Privacy Framework (including UK Extension and Swiss U.S.); EU Standard Contractual Clauses with UK International Data Transfer Addendum and Swiss adaptations',
    link: 'https://posthog.com/privacy',
    availability: 'where_configured',
    availabilityLabel: 'Where analytics is enabled',
  },
  {
    name: 'Resend',
    purpose:
      'Transactional email, including invitations, alerts, passwordless sign-in messages, and Supabase Auth delivery (password reset, magic-link, and one-time-code emails) via SMTP where configured.',
    dataProcessed: 'Recipient email addresses, message metadata, and delivery events.',
    location: 'United States',
    region: 'United States',
    transferMechanism:
      'EU Standard Contractual Clauses (Module 2 and Module 3) with UK Addendum; EU U.S. Data Privacy Framework and UK Extension',
    link: 'https://resend.com/legal/privacy-policy',
    availability: 'where_configured',
    availabilityLabel: 'Where email is configured',
  },
  {
    name: 'TypeSafe AI',
    purpose:
      'Calibrated classification of CSV column headers during CSV ingestion (Jev System One model): which canonical FSMA 204 field an unrecognised column holds, and, for a file that declares no critical tracking event, which one its rows record.',
    dataProcessed:
      'CSV column headers; when the uploader declares a single CTE for the file, that canonical CTE name (for example "shipping"); and, only where sample values are explicitly enabled, PII-redacted sample cell values for unrecognised columns. Never whole rows or files.',
    location: 'United States',
    region: '',
    transferMechanism:
      'EU Standard Contractual Clauses (Module 2 and Module 3); UK International Data Transfer Addendum',
    link: 'https://typesafe.ai/legal/privacy',
    availability: 'where_configured',
    availabilityLabel: 'Where AI CSV suggestions are enabled',
  },
  {
    name: 'Cloudflare R2',
    purpose: 'Object storage for uploaded evidence files and generated artifacts.',
    dataProcessed:
      'Raw uploads, normalized JSON, parsed text extracts, and generated artifacts.',
    location: 'United States / global edge',
    region: '',
    transferMechanism:
      'EU U.S. Data Privacy Framework (including UK Extension and Swiss U.S.); EU Standard Contractual Clauses (Module 2 and Module 3) with UK International Data Transfer Addendum',
    link: 'https://www.cloudflare.com/privacypolicy/',
    availability: 'where_configured',
    availabilityLabel: 'Where object storage is configured',
  },
  {
    name: 'OpenAI',
    purpose:
      'AI-assisted document extraction, OCR enrichment, and classification workflows.',
    dataProcessed:
      'Uploaded document text, label images, and extracted field candidates submitted for enabled AI workflows.',
    location: 'United States / multi-region',
    region: '',
    transferMechanism:
      'EU Standard Contractual Clauses for EEA and Swiss transfers; UK International Data Transfer Addendum for UK transfers',
    link: 'https://openai.com/policies/privacy-policy',
    availability: 'not_in_production',
    availabilityLabel: 'Not used in production; may be enabled only after notice',
  },
  {
    name: 'Google Cloud Vertex AI',
    purpose: 'Gemini-assisted extraction and classification for configured AI workflows.',
    dataProcessed:
      'Uploaded document text, label images, and extracted field candidates submitted for enabled AI workflows.',
    location: 'United States (us-central1)',
    region: 'Customer selected Google Cloud region',
    transferMechanism:
      'EU Standard Contractual Clauses or an Alternative Transfer Solution adopted by Google',
    link: 'https://cloud.google.com/terms/cloud-privacy-notice',
    availability: 'not_in_production',
    availabilityLabel: 'Not used in production; may be enabled only after notice',
  },
  {
    name: 'LlamaCloud',
    purpose:
      'Planned document extraction for admin bulk PDF uploads. Not enabled in production; enablement pending legal review and customer notice.',
    dataProcessed:
      'Complete uploaded document file content sent for an extraction job, plus extraction outputs returned to RegEngine. RegEngine attempts to delete the vendor side file when the job ends and disables vendor result caching by default.',
    location:
      'United States by default (LlamaCloud NA). EU Frankfurt only if an EU endpoint is configured.',
    region:
      'United States (AWS us-east-1) by default; European Union Frankfurt (AWS eu-central-1) when using the EU endpoint',
    transferMechanism:
      'EU Standard Contractual Clauses (Module 2 and Module 3) and UK International Data Transfer Addendum (self serve DPA incorporated via Terms of Service)',
    link: 'https://www.llamaindex.ai/legal/terms-of-service',
    availability: 'not_in_production',
    availabilityLabel:
      'Planned: document extraction for admin bulk PDF uploads; not enabled in production as of Oct 28, 2026; enablement pending legal review and customer notice',
  },
];
