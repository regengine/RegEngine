import { CodePlayground } from '@/components/playground/CodePlayground';

import { PageContainer } from '@/components/layout/page-container';
import { AlertTriangle, Code, Zap, Shield } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

const ingestExample = `// Ingest a Critical Tracking Event (FSMA 204)
const response = await fetch('https://www.regengine.co/api/v1/webhooks/ingest', {
  method: 'POST',
  headers: {
    'X-RegEngine-API-Key': 'YOUR_API_KEY',
    'X-Tenant-ID': 'YOUR_TENANT_UUID',
    'Content-Type': 'application/json',
  },
  body: JSON.stringify({
    source: 'erp',
    events: [{
      cte_type: 'receiving',
      traceability_lot_code: '00012345678901-LOT-2026-001',
      product_description: 'Romaine Lettuce',
      quantity: 500,
      unit_of_measure: 'cases',
      location_name: 'Distribution Center #4',
      timestamp: new Date().toISOString(),
      kdes: {
        receive_date: '2026-03-11',
        receiving_location: 'Distribution Center #4',
      }
    }]
  })
});

const result = await response.json();
console.log('Accepted:', result.accepted);
console.log('SHA-256 hash:', result.events?.[0]?.sha256_hash);
console.log('Chain hash:', result.events?.[0]?.chain_hash);
`;

const verifyExample = `// Verify event chain integrity
const response = await fetch(
  'https://www.regengine.co/api/v1/epcis/chain/verify?tenant_id=YOUR_TENANT_UUID',
  {
    headers: { 'X-RegEngine-API-Key': 'YOUR_API_KEY' }
  }
);

const result = await response.json();
if (result.valid) {
  console.log('✅ Chain integrity verified');
  console.log('Events verified:', result.events_checked);
  console.log('Hash mismatches:', result.hash_failures);
} else {
  console.error('❌ Chain integrity failed:', result.reason);
}
`;

const demoExample = `// Try JavaScript here!
const lots = [
  { id: 'LOT-2026-001', product: 'Romaine Lettuce', ctes: 3 },
  { id: 'LOT-2026-002', product: 'Baby Spinach', ctes: 5 },
  { id: 'LOT-2026-003', product: 'Cherry Tomatoes', ctes: 2 },
];

console.log('Total lots tracked:', lots.length);

lots.forEach(lot => {
  console.log(\`\${lot.product} (\${lot.id}): \${lot.ctes} CTEs\`);
});

const totalCTEs = lots.reduce((sum, lot) => sum + lot.ctes, 0);
console.log('Total CTEs across all lots:', totalCTEs);
`;

export default function PlaygroundPage() {
    return (
        <div className="min-h-screen bg-gradient-to-b from-background to-muted/20">
            <PageContainer>
                {/* Hero */}
                <div className="mb-12">
                    <div className="flex items-center gap-3 mb-4">
                        <Code className="h-10 w-10 text-primary" />
                        <h1 className="text-4xl font-bold">API Playground</h1>
                    </div>
                    <p className="text-xl text-muted-foreground max-w-3xl">
                        Test API calls interactively with live code execution and instant feedback.
                    </p>
                </div>

                <div className="mb-6 p-3 rounded-lg bg-amber-50 dark:bg-amber-950/20 border border-amber-200 dark:border-amber-800 flex items-center gap-2 text-amber-800 dark:text-amber-200 text-sm">
                    <AlertTriangle className="h-4 w-4 shrink-0" />
                    <span>Demo Data — This page shows simulated data. Connect your backend to see live metrics.</span>
                </div>

                {/* Safety Notice */}
                <div className="bg-amber-50 dark:bg-amber-900/20 border border-amber-200 dark:border-amber-800 rounded-lg p-6 mb-8">
                    <div className="flex items-start gap-3">
                        <Shield className="h-6 w-6 text-amber-600 flex-shrink-0 mt-1" />
                        <div>
                            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                Sandboxed Environment
                            </h3>
                            <p className="text-gray-700 dark:text-gray-300 text-sm">
                                Code runs in your browser in a sandboxed environment. For actual API calls, use your API key
                                from the <Link href="/api-keys" className="text-primary hover:underline">API Keys page</Link>.
                            </p>
                        </div>
                    </div>
                </div>

                {/* Quick Demo */}
                <div className="mb-12">
                    <h2 className="text-2xl font-bold mb-4 flex items-center gap-2">
                        <Zap className="h-6 w-6 text-yellow-500" />
                        Quick Demo
                    </h2>
                    <CodePlayground
                        title="JavaScript Sandbox"
                        description="Try any JavaScript code - no API key needed"
                        initialCode={demoExample}
                        language="javascript"
                        height="500px"
                    />
                </div>

                {/* FSMA 204 API Examples */}
                <div className="space-y-8">
                    <h2 className="text-2xl font-bold">FSMA 204 API Examples</h2>

                    <CodePlayground
                        title="Ingest a Critical Tracking Event"
                        description="POST a CTE to the RegEngine ingest endpoint"
                        initialCode={ingestExample}
                        language="javascript"
                        height="600px"
                    />

                    <CodePlayground
                        title="Verify Chain Integrity"
                        description="Cryptographically verify your entire event chain"
                        initialCode={verifyExample}
                        language="javascript"
                        height="500px"
                    />
                </div>

                {/* Links */}
                <div className="mt-12 p-6 bg-slate-50 dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700">
                    <h3 className="font-semibold mb-4">Next Steps</h3>
                    <div className="grid md:grid-cols-3 gap-4">
                        <Link href="/docs/api">
                            <Button variant="outline" className="w-full">
                                API Reference
                            </Button>
                        </Link>
                        <Link href="/api-keys">
                            <Button variant="outline" className="w-full">
                                Get API Key
                            </Button>
                        </Link>
                        <Link href="/docs/fsma-204">
                            <Button variant="outline" className="w-full">
                                Documentation
                            </Button>
                        </Link>
                    </div>
                </div>
            </PageContainer>
        </div>
    );
}
