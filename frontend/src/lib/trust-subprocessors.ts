export type SubprocessorAvailability = 'default' | 'where_configured';

export interface TrustSubprocessor {
  name: string;
  purpose: string;
  dataProcessed: string;
  location: string;
  link: string;
  availability: SubprocessorAvailability;
  availabilityLabel: string;
}

export const TRUST_SUBPROCESSORS: TrustSubprocessor[] = [
  {
    name: 'Supabase',
    purpose: 'Authentication for developer-portal accounts and a legacy session-validation path; stores developer-portal API-key records and pre-sales assessment leads. Core tenant workspace data is stored in PostgreSQL managed by Railway.',
    dataProcessed: 'Developer-portal account records, API-key records, pre-sales assessment leads, and authentication metadata.',
    location: 'United States; project region per executed agreement/current DPA',
    link: 'https://supabase.com/privacy',
    availability: 'default',
    availabilityLabel: 'Default platform processor',
  },
  {
    name: 'Railway',
    purpose: 'Platform hosting the RegEngine application and the core PostgreSQL database for tenant workspace data.',
    dataProcessed: 'Workspace records, evidence ledger rows, API requests, application logs, and workflow metadata.',
    location: 'United States',
    link: 'https://railway.app/legal/privacy',
    availability: 'default',
    availabilityLabel: 'Default platform processor',
  },
  {
    name: 'Vercel',
    purpose: 'Frontend hosting, edge delivery, and authenticated request routing.',
    dataProcessed: 'Authenticated web requests, CDN metadata, and limited edge logs.',
    location: 'United States / global CDN',
    link: 'https://vercel.com/legal/privacy-policy',
    availability: 'default',
    availabilityLabel: 'Default platform processor',
  },
  {
    name: 'Sentry',
    purpose: 'Server, edge, and backend error monitoring with PII scrubbing configured where available.',
    dataProcessed: 'Error events, stack traces, request metadata, and environment diagnostics. Browser replay capture is not enabled by default.',
    location: 'United States',
    link: 'https://sentry.io/privacy/',
    availability: 'where_configured',
    availabilityLabel: 'Where configured',
  },
  {
    name: 'Stripe',
    purpose: 'Billing, invoices, payment processing, and tax support.',
    dataProcessed: 'Billing contact information, subscription metadata, payment processor tokens, and invoice history.',
    location: 'United States',
    link: 'https://stripe.com/privacy',
    availability: 'where_configured',
    availabilityLabel: 'Where billing is enabled',
  },
  {
    name: 'PostHog',
    purpose: 'Privacy-conscious product analytics after consent or workspace enablement.',
    dataProcessed: 'Workspace-scoped product events, pseudonymous identifiers, and consent metadata.',
    location: 'United States',
    link: 'https://posthog.com/privacy',
    availability: 'where_configured',
    availabilityLabel: 'Where analytics is enabled',
  },
  {
    name: 'Resend',
    purpose: 'Transactional email, including invitations, alerts, passwordless sign-in messages, and Supabase Auth delivery (password reset, magic-link, and one-time-code emails) via SMTP where configured.',
    dataProcessed: 'Recipient email addresses, message metadata, and delivery events.',
    location: 'United States',
    link: 'https://resend.com/legal/privacy-policy',
    availability: 'where_configured',
    availabilityLabel: 'Where email is configured',
  },
  {
    name: 'OpenAI',
    purpose: 'AI-assisted document extraction, OCR enrichment, and classification workflows.',
    dataProcessed: 'Uploaded document text, label images, and extracted field candidates submitted for enabled AI workflows.',
    location: 'United States / multi-region',
    link: 'https://openai.com/policies/privacy-policy',
    availability: 'where_configured',
    availabilityLabel: 'Where AI extraction is enabled',
  },
  {
    name: 'Google Cloud Vertex AI',
    purpose: 'Gemini-assisted extraction and classification for configured AI workflows.',
    dataProcessed: 'Uploaded document text, label images, and extracted field candidates submitted for enabled AI workflows.',
    location: 'United States (us-central1)',
    link: 'https://cloud.google.com/terms/cloud-privacy-notice',
    availability: 'where_configured',
    availabilityLabel: 'Where AI extraction is enabled',
  },
  {
    name: 'Cloudflare R2',
    purpose: 'Object storage for uploaded evidence files and generated artifacts.',
    dataProcessed: 'Raw uploads, normalized JSON, parsed text extracts, and generated artifacts.',
    location: 'United States / global edge',
    link: 'https://www.cloudflare.com/privacypolicy/',
    availability: 'where_configured',
    availabilityLabel: 'Where object storage is configured',
  },
];
