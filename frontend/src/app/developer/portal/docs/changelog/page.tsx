'use client';

import { FileText, Tag } from 'lucide-react';

export default function ChangelogPage() {
  const entries = [
    {
      date: 'March 2026',
      version: '1.5.0',
      title: 'Developer Portal Launch',
      changes: [
        'Developer Portal invite-only access',
        'API key management dashboard',
        'Interactive API documentation',
        'Webhook event delivery tracking'
      ]
    },
    {
      date: 'February 2026',
      version: '1.4.0',
      title: 'Webhook & Compliance Improvements',
      changes: [
        'Webhook event delivery system',
        'EPCIS 2.0 endpoint support',
        'Chain verification endpoint',
        'Real-time event notifications'
      ]
    },
    {
      date: 'January 2026',
      version: '1.3.0',
      title: 'Recall & Decode Features',
      changes: [
        'Recall simulation API endpoint',
        'QR code decode endpoint',
        'Barcode scanning support',
        'Batch event processing'
      ]
    },
    {
      date: 'December 2025',
      version: '1.2.0',
      title: 'Compliance Scoring',
      changes: [
        'Compliance scoring API',
        'FDA export endpoint',
        'Audit report generation',
        'Regulatory tracking'
      ]
    },
    {
      date: 'November 2025',
      version: '1.0.0',
      title: 'Initial API Launch',
      changes: [
        'CTE ingestion endpoint',
        'Event query API',
        'API key authentication',
        'Rate limiting system'
      ]
    }
  ];

  return (
    <div className="space-y-8 pb-12">
      <div>
        <h1 className="text-3xl font-bold mb-2" style={{ color: 'var(--re-text-primary)' }}>
          Changelog
        </h1>
        <p className="text-lg" style={{ color: 'var(--re-text-muted)' }}>
          API updates and feature releases
        </p>
      </div>

      <div className="space-y-6">
        {entries.map((entry, index) => (
          <div
            key={index}
            style={{
              background: 'rgba(255,255,255,0.02)',
              border: '1px solid rgba(255,255,255,0.06)',
              borderRadius: '8px',
              padding: '24px'
            }}
          >
            <div className="flex items-start justify-between mb-4 gap-4">
              <div className="flex items-start gap-3">
                <FileText size={20} style={{ color: 'var(--re-brand)', marginTop: '2px' }} />
                <div>
                  <h2 className="text-xl font-semibold" style={{ color: 'var(--re-text-primary)' }}>
                    {entry.title}
                  </h2>
                  <p style={{ color: 'var(--re-text-muted)', fontSize: '14px' }}>
                    {entry.date}
                  </p>
                </div>
              </div>
              <div
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                  background: 'rgba(255,255,255,0.08)',
                  border: '1px solid rgba(255,255,255,0.12)',
                  borderRadius: '6px',
                  padding: '6px 12px',
                  whiteSpace: 'nowrap'
                }}
              >
                <Tag size={14} style={{ color: 'var(--re-brand)' }} />
                <span style={{ color: 'var(--re-text-primary)', fontSize: '13px', fontWeight: '600' }}>
                  v{entry.version}
                </span>
              </div>
            </div>

            <ul style={{ color: 'var(--re-text-muted)', paddingLeft: '24px', space: '8px' }}>
              {entry.changes.map((change, changeIndex) => (
                <li key={changeIndex} style={{ marginBottom: '8px' }}>
                  {change}
                </li>
              ))}
            </ul>
          </div>
        ))}
      </div>
    </div>
  );
}