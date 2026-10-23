import type { Metadata } from 'next';
import { ApiReferenceClient } from './ApiReferenceClient';

export const metadata: Metadata = {
    title: 'API Reference | RegEngine',
    description:
        'RegEngine API reference for FSMA 204 traceability records, advisory compliance validation, JSON events API ingestion, and FDA-oriented sortable exports.',
    openGraph: {
      title: 'API Reference',
      description: 'RegEngine API reference for FSMA 204 traceability records, advisory compliance validation, JSON events API ingestion, and FDA-oriented sortable exports.',
      url: 'https://regengine.co/docs/api',
      type: 'website',
    },
};

export default function ApiReferencePage() {
    return <ApiReferenceClient />;
}
