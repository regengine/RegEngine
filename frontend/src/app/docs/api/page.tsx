import type { Metadata } from 'next';
import { ApiReferenceClient } from './ApiReferenceClient';

export const metadata: Metadata = {
    title: 'API Reference | RegEngine',
    description:
        'RegEngine API reference for FSMA 204 traceability records, advisory compliance validation, and FDA-oriented sortable exports. The JSON events API is available by request with an issued API key.',
    openGraph: {
      title: 'API Reference',
      description: 'RegEngine API reference for FSMA 204 traceability records, advisory compliance validation, and FDA-oriented sortable exports. The JSON events API is available by request with an issued API key.',
      url: 'https://regengine.co/docs/api',
      type: 'website',
    },
};

export default function ApiReferencePage() {
    return <ApiReferenceClient />;
}
