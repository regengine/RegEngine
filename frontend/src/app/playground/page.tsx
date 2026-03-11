import { CodePlayground } from '@/components/playground/CodePlayground';

import { PageContainer } from '@/components/layout/page-container';
import { AlertTriangle, Code, Zap, Shield } from 'lucide-react';
import Link from 'next/link';
import { Button } from '@/components/ui/button';

const nuclearExample = `// Nuclear SDK - Create Compliance Record
import { NuclearCompliance } from '@regengine/nuclear-sdk';

const nuclear = new NuclearCompliance(process.env.API_KEY);

const record = await nuclear.records.create({
  facilityId: 'NPP-UNIT-1',
  reactorId: 'UNIT-1',
  docketNumber: '50-12345',
  recordType: 'CYBER_SECURITY_PLAN',
  classification: 'STANDARD',
  content: {
    programElement: 'Defensive Architecture',
    reviewDate: '2026-01-25',
    reviewer: {
      name: 'John Smith',
      license: 'SRO-12345'
    }
  },
  regulatoryRefs: [
    { cfr: '10-CFR-73.54', note: 'Cybersecurity Program evidence' }
  ],
  retentionPolicyId: 'NRC_73_54_LICENSE_LIFE_PLUS_3'
});

console.log('Record ID:', record.record.id);
console.log('Content Hash:', record.record.integrity.contentHash);
console.log('Sealed:', record.record.integrity.sealed);
`;

const verifyExample = `// Verify Record Integrity
import { NuclearCompliance } from '@regengine/nuclear-sdk';

const nuclear = new NuclearCompliance(process.env.API_KEY);

const recordId = 'rec_0193abc...';
const verification = await nuclear.records.verify(recordId);

if (verification.status === 'valid') {
  console.log('✅ Record integrity verified');
  console.log('Content hash valid:', verification.results.contentHashValid);
  console.log('Chain intact:', verification.results.chainIntact);
} else {
  console.error('❌ Verification failed:', verification.reason);
}
`;

const demoExample = `// Try JavaScript here!
const facilities = [
  { id: 'NPP-1', name: 'Unit 1', status: 'operational' },
  { id: 'NPP-2', name: 'Unit 2', status: 'maintenance' }
];

console.log('Total facilities:', facilities.length);

facilities.forEach(f => {
  console.log(\`\${f.name}: \${f.status}\`);
});

// Calculate something
const operationalCount = facilities.filter(
  f => f.status === 'operational'
).length;

console.log('Operational units:', operationalCount);
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

                {/* Nuclear SDK Examples */}
                <div className="space-y-8">
                    <h2 className="text-2xl font-bold">Nuclear SDK Examples</h2>

                    <CodePlayground
                        title="Create Compliance Record"
                        description="Example: Creating an immutable compliance record"
                        initialCode={nuclearExample}
                        language="typescript"
                        height="600px"
                    />

                    <CodePlayground
                        title="Verify Record Integrity"
                        description="Example: Cryptographic verification of a compliance record"
                        initialCode={verifyExample}
                        language="typescript"
                        height="500px"
                    />
                </div>

                {/* Links */}
                <div className="mt-12 p-6 bg-slate-50 dark:bg-slate-900 rounded-lg border border-slate-200 dark:border-slate-700">
                    <h3 className="font-semibold mb-4">Next Steps</h3>
                    <div className="grid md:grid-cols-3 gap-4">
                        <Link href="/api-reference/nuclear">
                            <Button variant="outline" className="w-full">
                                API Reference
                            </Button>
                        </Link>
                        <Link href="/api-keys">
                            <Button variant="outline" className="w-full">
                                Get API Key
                            </Button>
                        </Link>
                        <Link href="/docs/nuclear">
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
