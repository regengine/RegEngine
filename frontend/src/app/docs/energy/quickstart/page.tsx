import Link from 'next/link';
import { Zap, Terminal, Check } from 'lucide-react';

export default function EnergyQuickstart() {
    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                {/* Breadcrumb */}
                <nav className="mb-8 text-sm">
                    <Link href="/docs" className="text-blue-600 hover:text-blue-800">Docs</Link>
                    <span className="mx-2 text-gray-400">/</span>
                    <Link href="/docs/energy" className="text-blue-600 hover:text-blue-800">Energy</Link>
                    <span className="mx-2 text-gray-400">/</span>
                    <span className="text-gray-600 dark:text-gray-400">Quickstart</span>
                </nav>

                {/* Title */}
                <div className="mb-12">
                    <div className="flex items-center gap-3 mb-4">
                        <Zap className="h-10 w-10 text-blue-600" />
                        <h1 className="text-4xl font-bold text-gray-900 dark:text-gray-100">
                            Energy API Quickstart
                        </h1>
                    </div>
                    <p className="text-xl text-gray-600 dark:text-gray-400">
                        Create your first NERC CIP-013 compliance snapshot in 5 minutes
                    </p>
                </div>

                {/* Progress Steps */}
                <div className="mb-12 flex items-center gap-4">
                    {[1, 2, 3, 4].map((step) => (
                        <div key={step} className="flex items-center gap-2">
                            <div className="w-8 h-8 rounded-full bg-blue-600 text-white flex items-center justify-center font-semibold">
                                {step}
                            </div>
                            {step < 4 && <div className="w-12 h-1 bg-blue-200 dark:bg-blue-800" />}
                        </div>
                    ))}
                </div>

                {/* Content */}
                <div className="prose dark:prose-invert max-w-none">
                    {/* Step 1 */}
                    <h2 id="step-1" className="flex items-center gap-3">
                        <span className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white text-lg font-bold">1</span>
                        Get Your API Key
                    </h2>
                    <p>
                        First, generate an API key for the Energy vertical.
                    </p>
                    <Link
                        href="/api-keys"
                        className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700 transition-colors no-underline"
                    >
                        <Terminal className="h-5 w-5" />
                        Generate API Key
                    </Link>

                    {/* Step 2 */}
                    <h2 id="step-2" className="flex items-center gap-3 mt-12">
                        <span className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white text-lg font-bold">2</span>
                        Install the SDK
                    </h2>
                    <p>
                        Install the RegEngine Energy SDK in your project.
                    </p>
                    <div className="bg-gray-900 dark:bg-black rounded-lg p-4 font-mono text-sm text-green-400 not-prose overflow-x-auto">
                        <div className="mb-2 text-gray-500"># Using npm</div>
                        <div>npm install @regengine/energy-sdk</div>
                        <div className="mt-4 text-gray-500"># Using yarn</div>
                        <div>yarn add @regengine/energy-sdk</div>
                        <div className="mt-4 text-gray-500"># Using pnpm</div>
                        <div>pnpm add @regengine/energy-sdk</div>
                    </div>

                    {/* Step 3 */}
                    <h2 id="step-3" className="flex items-center gap-3 mt-12">
                        <span className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white text-lg font-bold">3</span>
                        Create Your First Snapshot
                    </h2>
                    <p>
                        Use the SDK to create an immutable compliance snapshot.
                    </p>
                    <div className="bg-gray-900 dark:bg-black rounded-lg p-4 font-mono text-sm not-prose overflow-x-auto">
                        <pre className="text-green-400"><code>{`import { EnergyCompliance } from '@regengine/energy-sdk';

// Initialize with your API key
const energy = new EnergyCompliance(process.env.REGENGINE_API_KEY);

// Create compliance snapshot
async function createSnapshot() {
  const snapshot = await energy.snapshots.create({
    substationId: 'ALPHA-001',
    systemStatus: 'NOMINAL',
    assets: [
      {
        id: 'T1',
        type: 'TRANSFORMER',
        firmwareVersion: '2.4.1',
        vendorVerified: true,
        lastUpdate: new Date().toISOString()
      }
    ],
    espConfig: {
      firewallVersion: '2.4.1',
      idsEnabled: true,
      updateProcedure: 'VERIFIED_SOURCE_ONLY'
    },
    regulatory: {
      standard: 'NERC-CIP-013-1',
      auditReady: true
    }
  });

  console.log('✅ Snapshot created:', snapshot.id);
  console.log('🔒 Immutable hash:', snapshot.contentHash);
  console.log('⛓️  Chain status:', snapshot.chainStatus);
  
  return snapshot;
}

createSnapshot().catch(console.error);`}</code></pre>
                    </div>

                    {/* Step 4 */}
                    <h2 id="step-4" className="flex items-center gap-3 mt-12">
                        <span className="flex items-center justify-center w-8 h-8 rounded-full bg-blue-600 text-white text-lg font-bold">4</span>
                        Verify Integrity
                    </h2>
                    <p>
                        Verify the cryptographic integrity of your snapshot.
                    </p>
                    <div className="bg-gray-900 dark:bg-black rounded-lg p-4 font-mono text-sm not-prose overflow-x-auto">
                        <pre className="text-green-400"><code>{`// Verify snapshot integrity
async function verifySnapshot(snapshotId) {
  const verification = await energy.snapshots.verify(snapshotId);
  
  if (verification.valid) {
    console.log('✅ Snapshot is valid');
    console.log('   Hash verified:', verification.hashValid);
    console.log('   Chain intact:', verification.chainIntact);
  } else {
    console.log('❌ Snapshot verification failed');
    console.log('   Reason:', verification.reason);
  }
  
  return verification;
}

verifySnapshot(snapshot.id).catch(console.error);`}</code></pre>
                    </div>

                    {/* Success */}
                    <div className="bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg p-6 mt-12 not-prose">
                        <div className="flex items-start gap-3">
                            <Check className="h-6 w-6 text-green-600 flex-shrink-0 mt-1" />
                            <div>
                                <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                    Congratulations! 🎉
                                </h3>
                                <p className="text-gray-700 dark:text-gray-300 mb-4">
                                    You've created your first NERC CIP-013 compliance snapshot. The record is now:
                                </p>
                                <ul className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
                                    <li className="flex items-center gap-2">
                                        <Check className="h-4 w-4 text-green-600" />
                                        <span>Immutably stored in the database</span>
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <Check className="h-4 w-4 text-green-600" />
                                        <span>Cryptographically verifiable</span>
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <Check className="h-4 w-4 text-green-600" />
                                        <span>Linked to the chain of custody</span>
                                    </li>
                                    <li className="flex items-center gap-2">
                                        <Check className="h-4 w-4 text-green-600" />
                                        <span>Audit-ready for NERC inspections</span>
                                    </li>
                                </ul>
                            </div>
                        </div>
                    </div>

                    {/* Next Steps */}
                    <h2 className="mt-12">Next Steps</h2>
                    <div className="grid md:grid-cols-2 gap-4 not-prose">
                        <Link href="/api-reference/energy" className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-blue-500 transition-colors">
                            <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                                API Reference
                            </h4>
                            <p className="text-sm text-gray-600 dark:text-gray-400">
                                Explore all available methods and options
                            </p>
                        </Link>

                        <Link href="/docs/energy" className="p-4 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-blue-500 transition-colors">
                            <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-1">
                                Full Documentation
                            </h4>
                            <p className="text-sm text-gray-600 dark:text-gray-400">
                                Learn about advanced features and best practices
                            </p>
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
}
