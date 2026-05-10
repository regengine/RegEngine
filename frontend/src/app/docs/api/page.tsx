import type { Metadata } from 'next';
import { ApiReferenceClient } from './ApiReferenceClient';

export const metadata: Metadata = {
    title: 'API Reference | RegEngine',
    description:
        'RegEngine API reference for FSMA 204 traceability records, advisory compliance validation, webhook ingestion, and §1.1455(c)-formatted exports.',
};

export default function ApiReferencePage() {
    return <ApiReferenceClient />;
}
