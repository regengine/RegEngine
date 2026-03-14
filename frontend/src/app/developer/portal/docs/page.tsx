'use client';

import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { BookOpen, Terminal, ArrowRight } from 'lucide-react';
import { Button } from '@/components/ui/button';

const API_SECTIONS = [
    {
        title: 'Ingestion API',
        description: 'Document fetching, normalization, and CTE processing',
        endpoints: [
            { method: 'POST', path: '/api/v1/webhooks/ingest', desc: 'Ingest Critical Tracking Events (batch)' },
            { method: 'POST', path: '/api/v1/epcis/events', desc: 'Ingest EPCIS 2.0 events' },
            { method: 'GET', path: '/api/v1/epcis/events/:id', desc: 'Get event by ID' },
        ],
    },
    {
        title: 'Compliance API',
        description: 'Compliance scoring, snapshots, and FDA export',
        endpoints: [
            { method: 'GET', path: '/api/v1/compliance/score/:tenant_id', desc: 'Get compliance risk score' },
            { method: 'GET', path: '/api/v1/fda/export', desc: 'Export FDA compliance package' },
            { method: 'GET', path: '/api/v1/epcis/chain/verify', desc: 'Verify event chain integrity' },
        ],
    },
    {
        title: 'Recall & Simulation',
        description: 'Recall drills, readiness scoring, and audit trails',
        endpoints: [
            { method: 'POST', path: '/api/v1/recall-simulations/run', desc: 'Run recall simulation drill' },
            { method: 'POST', path: '/api/v1/qr/decode', desc: 'Decode GS1 / GTIN barcode' },
        ],
    },
];

const EXAMPLE_CURL = `curl -X POST https://www.regengine.co/api/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: rge_dev_your_key_here" \\
  -H "Content-Type: application/json" \\
  -d '{
    "events": [{
      "event_type": "receiving",
      "tlc": "LOT-2024-001",
      "product_description": "Fresh Romaine Lettuce",
      "gtin": "00614141000012",
      "quantity": 500,
      "unit": "cases",
      "timestamp": "2025-03-10T14:30:00Z"
    }]
  }'`;

export default function DocsPage() {
    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold" style={{ color: 'var(--re-text-primary)' }}>API Documentation</h1>
                    <p className="text-sm mt-1" style={{ color: 'var(--re-text-muted)' }}>
                        Authenticated endpoint reference for your integration.
                    </p>
                </div>
                <Link href="/docs/api">
                    <Button variant="outline" size="sm" style={{ borderColor: 'rgba(255,255,255,0.1)', color: 'var(--re-text-muted)' }}>
                        Full Public Docs <ArrowRight className="w-3 h-3 ml-1" />
                    </Button>
                </Link>
            </div>

            {/* Auth reminder */}
            <Card style={{ background: 'rgba(16,185,129,0.06)', border: '1px solid rgba(16,185,129,0.2)' }}>
                <CardContent className="py-3 flex items-start gap-3">
                    <Terminal className="w-4 h-4 mt-0.5 flex-shrink-0" style={{ color: 'var(--re-brand)' }} />
                    <div>
                        <p className="text-sm font-medium" style={{ color: 'var(--re-text-primary)' }}>Authentication</p>
                        <p className="text-xs mt-1" style={{ color: 'var(--re-text-muted)' }}>
                            All requests require <code className="font-mono px-1 rounded text-xs" style={{ background: 'rgba(0,0,0,0.2)' }}>X-RegEngine-API-Key: rge_dev_your_key</code> header.
                            Generate keys from the <Link href="/developer/portal/keys" style={{ color: 'var(--re-brand)' }}>API Keys</Link> page.
                        </p>
                    </div>
                </CardContent>
            </Card>

            {/* Endpoint sections */}
            {API_SECTIONS.map((section) => (
                <Card key={section.title} style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                    <CardHeader className="pb-2">
                        <CardTitle className="text-base flex items-center gap-2" style={{ color: 'var(--re-text-primary)' }}>
                            <BookOpen className="w-4 h-4" style={{ color: 'var(--re-brand)' }} />
                            {section.title}
                        </CardTitle>
                        <p className="text-xs" style={{ color: 'var(--re-text-muted)' }}>{section.description}</p>
                    </CardHeader>
                    <CardContent className="space-y-1">
                        {section.endpoints.map((ep, i) => (
                            <div key={i} className="flex items-center gap-3 py-2 px-3 rounded" style={{ background: 'rgba(0,0,0,0.1)' }}>
                                <Badge
                                    variant="outline"
                                    className="font-mono text-xs w-14 justify-center flex-shrink-0"
                                    style={{
                                        color: ep.method === 'POST' ? 'var(--re-brand)' : '#60a5fa',
                                        borderColor: ep.method === 'POST' ? 'rgba(16,185,129,0.3)' : 'rgba(96,165,250,0.3)',
                                    }}
                                >
                                    {ep.method}
                                </Badge>
                                <code className="text-xs font-mono flex-1" style={{ color: 'var(--re-text-primary)' }}>{ep.path}</code>
                                <span className="text-xs" style={{ color: 'var(--re-text-muted)' }}>{ep.desc}</span>
                            </div>
                        ))}
                    </CardContent>
                </Card>
            ))}

            {/* Quick start example */}
            <Card style={{ background: 'rgba(255,255,255,0.02)', border: '1px solid rgba(255,255,255,0.06)' }}>
                <CardHeader className="pb-2">
                    <CardTitle className="text-base" style={{ color: 'var(--re-text-primary)' }}>Quick Start</CardTitle>
                </CardHeader>
                <CardContent>
                    <pre className="text-xs font-mono leading-relaxed p-4 rounded overflow-auto" style={{ background: 'rgba(0,0,0,0.3)', color: 'var(--re-text-muted)' }}>
                        <code>{EXAMPLE_CURL}</code>
                    </pre>
                </CardContent>
            </Card>
        </div>
    );
}
