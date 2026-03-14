'use client';

import { useState } from 'react';
import { CodeBlock } from '@/components/developer/CodeBlock';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import {
  Webhook,
  Send,
  Check,
  Loader2,
  AlertCircle,
} from 'lucide-react';

export default function WebhooksPage() {
  const [selectedEvent, setSelectedEvent] = useState('event.ingested');
  const [webhookUrl, setWebhookUrl] = useState('');
  const [loading, setLoading] = useState(false);
  const [deliveryStatus, setDeliveryStatus] = useState<{
    status: 'success' | 'error' | null;
    message?: string;
    time?: number;
  }>({ status: null });

  const eventTypes = [
    {
      name: 'event.ingested',
      description: 'Fired when a CTE is accepted and processed',
      payload: {
        event_type: 'event.ingested',
        timestamp: '2026-03-14T10:30:00Z',
        data: {
          id: 'evt_123abc',
          cte_id: 'cte_456def',
          status: 'accepted',
        },
      },
    },
    {
      name: 'event.rejected',
      description: 'Fired when a CTE fails validation',
      payload: {
        event_type: 'event.rejected',
        timestamp: '2026-03-14T10:30:00Z',
        data: {
          id: 'evt_124abc',
          cte_id: 'cte_457def',
          reason: 'Invalid signature',
        },
      },
    },
  ];

  const complianceEvents = [
    {
      name: 'compliance.score_changed',
      description: 'Fired when compliance score updates',
      payload: {
        event_type: 'compliance.score_changed',
        timestamp: '2026-03-14T10:30:00Z',
        data: {
          previous_score: 85,
          new_score: 92,
          chain_id: 'chain_123',
        },
      },
    },
    {
      name: 'recall.simulation_completed',
      description: 'Fired when a recall drill finishes',
      payload: {
        event_type: 'recall.simulation_completed',
        timestamp: '2026-03-14T10:30:00Z',
        data: {
          simulation_id: 'sim_789xyz',
          duration_ms: 4500,
          success: true,
        },
      },
    },
    {
      name: 'chain.integrity_warning',
      description: 'Fired when chain hash mismatch detected',
      payload: {
        event_type: 'chain.integrity_warning',
        timestamp: '2026-03-14T10:30:00Z',
        data: {
          chain_id: 'chain_123',
          expected_hash: 'abc123...',
          actual_hash: 'def456...',
        },
      },
    },
  ];

  const allEvents = [...eventTypes, ...complianceEvents];
  const currentEvent = allEvents.find((e) => e.name === selectedEvent);

  const handleSendTest = async () => {
    if (!webhookUrl) return;
    setLoading(true);
    setDeliveryStatus({ status: null });

    // Simulate network delay
    await new Promise((resolve) => setTimeout(resolve, 1200));

    setDeliveryStatus({
      status: 'success',
      message: 'Delivered',
      time: 89,
    });
    setLoading(false);
  };

  const pythonVerification = `import hmac
import hashlib
import json

def verify_webhook(payload, signature, secret):
    computed_sig = hmac.new(
        secret.encode(),
        payload.encode(),
        hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(computed_sig, signature)

# In your webhook handler
payload = request.body
signature = request.headers.get('X-RegEngine-Signature')
if verify_webhook(payload, signature, WEBHOOK_SECRET):
    data = json.loads(payload)
    # Process webhook
else:
    return 'Unauthorized', 401`;

  const nodeVerification = `import crypto from 'crypto';

function verifyWebhook(payload, signature, secret) {
  const computed = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');
  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(computed)
  );
}

// In your webhook handler
const payload = req.body;
const signature = req.headers['x-regengine-signature'];
if (verifyWebhook(payload, signature, WEBHOOK_SECRET)) {
  const data = JSON.parse(payload);
  // Process webhook
} else {
  return res.status(401).json({ error: 'Unauthorized' });
}`;

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-900 via-slate-800 to-slate-900 p-8">
      <div className="max-w-4xl mx-auto">
        {/* Header */}
        <div className="mb-12">
          <div className="flex items-center gap-3 mb-4">
            <Webhook className="w-8 h-8" style={{ color: 'var(--re-brand)' }} />
            <h1
              className="text-4xl font-bold"
              style={{ color: 'var(--re-text-primary)' }}
            >
              Webhooks
            </h1>
          </div>
          <p
            style={{ color: 'var(--re-text-muted)' }}
            className="text-lg"
          >
            Receive real-time event delivery to your application
          </p>
        </div>

        {/* Event Types Section */}
        <section className="mb-12">
          <h2
            className="text-2xl font-bold mb-6"
            style={{ color: 'var(--re-text-primary)' }}
          >
            Event Types
          </h2>
          <div className="space-y-6">
            {allEvents.map((event) => (
              <div
                key={event.name}
                className="p-6 rounded-lg border border-slate-700"
                style={{ backgroundColor: 'rgba(30, 41, 59, 0.5)' }}
              >
                <div className="flex items-start justify-between mb-3">
                  <div>
                    <code
                      className="font-mono text-sm font-semibold"
                      style={{ color: 'var(--re-brand)' }}
                    >
                      {event.name}
                    </code>
                    <p
                      className="text-sm mt-1"
                      style={{ color: 'var(--re-text-muted)' }}
                    >
                      {event.description}
                    </p>
                  </div>
                </div>
                <CodeBlock snippets={[{ language: 'json', label: 'JSON', code: JSON.stringify(event.payload, null, 2) }]} />
              </div>
            ))}
          </div>
        </section>

        {/* Signature Verification Section */}
        <section className="mb-12">
          <h2
            className="text-2xl font-bold mb-6"
            style={{ color: 'var(--re-text-primary)' }}
          >
            Webhook Signature Verification
          </h2>
          <p
            className="mb-6"
            style={{ color: 'var(--re-text-muted)' }}
          >
            All webhooks include an <code className="bg-slate-700 px-2 py-1 rounded text-sm">X-RegEngine-Signature</code> header containing an HMAC-SHA256 signature. Verify this signature using your webhook secret.
          </p>

          <div className="space-y-6">
            <div>
              <h3
                className="font-semibold mb-3"
                style={{ color: 'var(--re-text-primary)' }}
              >
                Python
              </h3>
              <CodeBlock snippets={[{ language: 'python', label: 'Python', code: pythonVerification }]} />
            </div>

            <div>
              <h3
                className="font-semibold mb-3"
                style={{ color: 'var(--re-text-primary)' }}
              >
                Node.js
              </h3>
              <CodeBlock snippets={[{ language: 'javascript', label: 'Node.js', code: nodeVerification }]} />
            </div>
          </div>
        </section>

        {/* Test Webhook Section */}
        <section>
          <h2
            className="text-2xl font-bold mb-6"
            style={{ color: 'var(--re-text-primary)' }}
          >
            Test Webhook
          </h2>
          <div
            className="p-6 rounded-lg border border-slate-700"
            style={{ backgroundColor: 'rgba(30, 41, 59, 0.5)' }}
          >
            <div className="space-y-4">
              <div>
                <label
                  className="block text-sm font-medium mb-2"
                  style={{ color: 'var(--re-text-primary)' }}
                >
                  Event Type
                </label>
                <select
                  value={selectedEvent}
                  onChange={(e) => setSelectedEvent(e.target.value)}
                  className="w-full px-4 py-2 rounded-lg border border-slate-600 bg-slate-900"
                  style={{
                    color: 'var(--re-text-primary)',
                    borderColor: 'var(--re-text-muted)',
                  }}
                >
                  {allEvents.map((event) => (
                    <option key={event.name} value={event.name}>
                      {event.name}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label
                  className="block text-sm font-medium mb-2"
                  style={{ color: 'var(--re-text-primary)' }}
                >
                  Webhook URL
                </label>
                <input
                  type="url"
                  placeholder="https://example.com/webhooks"
                  value={webhookUrl}
                  onChange={(e) => setWebhookUrl(e.target.value)}
                  className="w-full px-4 py-2 rounded-lg border border-slate-600 bg-slate-900"
                  style={{
                    color: 'var(--re-text-primary)',
                    borderColor: 'var(--re-text-muted)',
                  }}
                />
              </div>

              <div>
                <label
                  className="block text-sm font-medium mb-3"
                  style={{ color: 'var(--re-text-primary)' }}
                >
                  Payload
                </label>
                <CodeBlock snippets={[{ language: 'json', label: 'JSON', code: JSON.stringify(currentEvent?.payload, null, 2) || '{}' }]} />
              </div>

              <div className="flex items-center gap-3">
                <Button
                  onClick={handleSendTest}
                  disabled={!webhookUrl || loading}
                  className="flex items-center gap-2"
                  style={{
                    backgroundColor: 'var(--re-brand)',
                    color: 'white',
                  }}
                >
                  {loading ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                  {loading ? 'Sending...' : 'Send Test Event'}
                </Button>

                {deliveryStatus.status === 'success' && (
                  <div className="flex items-center gap-2" style={{ color: 'var(--re-brand)' }}>
                    <Check className="w-4 h-4" />
                    <span className="text-sm font-medium">
                      Delivered · 200 OK · {deliveryStatus.time}ms
                    </span>
                  </div>
                )}

                {deliveryStatus.status === 'error' && (
                  <div className="flex items-center gap-2 text-red-400">
                    <AlertCircle className="w-4 h-4" />
                    <span className="text-sm font-medium">
                      {deliveryStatus.message}
                    </span>
                  </div>
                )}
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}