import Link from 'next/link';
import { Atom, Shield, AlertTriangle, CheckCircle, XCircle, Code, Book } from 'lucide-react';

export default function NuclearAPIReferencePage() {
    return (
        <div className="min-h-screen bg-gray-50 dark:bg-gray-900">
            {/* Hero */}
            <div className="bg-gradient-to-r from-orange-600 to-red-700">
                <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
                    <div className="flex items-center gap-4 mb-4">
                        <Atom className="h-12 w-12 text-white" />
                        <h1 className="text-4xl font-bold text-white">
                            Nuclear API Reference
                        </h1>
                    </div>
                    <p className="text-xl text-orange-100 max-w-3xl">
                        NRC-aligned compliance evidence API for nuclear facilities
                    </p>
                </div>
            </div>

            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
                {/* Quick Links */}
                <div className="grid md:grid-cols-3 gap-6 mb-12">
                    <Link href="#installation" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                        <Code className="h-8 w-8 text-orange-600 mb-3" />
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                            Installation
                        </h3>
                        <p className="text-gray-600 dark:text-gray-400 text-sm">
                            Get started with the SDK
                        </p>
                    </Link>

                    <Link href="#examples" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                        <Book className="h-8 w-8 text-orange-600 mb-3" />
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                            Code Examples
                        </h3>
                        <p className="text-gray-600 dark:text-gray-400 text-sm">
                            Working code samples
                        </p>
                    </Link>

                    <Link href="#safety-guarantees" className="p-6 bg-white dark:bg-gray-800 rounded-lg shadow hover:shadow-lg transition-shadow border border-gray-200 dark:border-gray-700">
                        <Shield className="h-8 w-8 text-orange-600 mb-3" />
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-2">
                            Safety Guarantees
                        </h3>
                        <p className="text-gray-600 dark:text-gray-400 text-sm">
                            What the system enforces
                        </p>
                    </Link>
                </div>

                {/* Regulatory Warning */}
                <div className="bg-orange-50 dark:bg-orange-900/20 border border-orange-200 dark:border-orange-800 rounded-lg p-6 mb-12">
                    <div className="flex items-start gap-3">
                        <AlertTriangle className="h-6 w-6 text-orange-600 flex-shrink-0 mt-1" />
                        <div>
                            <h3 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                Regulatory Boundaries
                            </h3>
                            <p className="text-gray-700 dark:text-gray-300 text-sm">
                                This API provides compliance evidence infrastructure. It does <strong>NOT</strong> ensure nuclear safety,
                                guarantee NRC compliance, or replace QA programs. Operators remain responsible for all regulatory obligations.
                            </p>
                        </div>
                    </div>
                </div>

                {/* Main Content */}
                <div className="prose dark:prose-invert max-w-none">
                    {/* Installation */}
                    <h2 id="installation">Installation</h2>
                    <div className="not-prose bg-gray-900 dark:bg-black rounded-lg p-4 mb-6 overflow-x-auto">
                        <pre className="text-green-400"><code>{`npm install @regengine/nuclear-sdk`}</code></pre>
                    </div>

                    <h3>Authentication</h3>
                    <p>
                        Get your API key from the <Link href="/api-keys" className="text-orange-600 hover:text-orange-800">API Keys page</Link>.
                        The SDK supports both service principals (API keys) and OAuth2 for human users.
                    </p>

                    {/* Examples */}
                    <h2 id="examples">Code Examples</h2>

                    <h3>Create a Compliance Record</h3>
                    <div className="not-prose bg-gray-900 dark:bg-black rounded-lg p-4 mb-6 overflow-x-auto">
                        <pre className="text-green-400"><code>{`import { NuclearCompliance } from '@regengine/nuclear-sdk';

const nuclear = new NuclearCompliance(process.env.REGENGINE_API_KEY);

// Create immutable compliance record
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
    { 
      cfr: '10-CFR-73.54', 
      note: 'Cybersecurity Program evidence' 
    }
  ],
  retentionPolicyId: 'NRC_73_54_LICENSE_LIFE_PLUS_3'
});

console.log('Record created:', record.record.id);
console.log('Content hash:', record.record.integrity.contentHash);
console.log('Sealed:', record.record.integrity.sealed);`}</code></pre>
                    </div>

                    <h3>Verify Record Integrity</h3>
                    <div className="not-prose bg-gray-900 dark:bg-black rounded-lg p-4 mb-6 overflow-x-auto">
                        <pre className="text-green-400"><code>{`// Independent cryptographic verification
const verification = await nuclear.records.verify(record.record.id);

if (verification.status === 'valid') {
  console.log('✅ Record integrity verified');
  console.log('   Content hash valid:', verification.results.contentHashValid);
  console.log('   Chain intact:', verification.results.chainIntact);
} else {
  console.error('❌ Record verification failed');
  console.error('   Reason:', verification.reason);
  console.error('   Expected hash:', verification.details.expectedContentHash);
  console.error('   Computed hash:', verification.details.computedContentHash);
}`}</code></pre>
                    </div>

                    <h3>Create Legal Hold</h3>
                    <div className="not-prose bg-gray-900 dark:bg-black rounded-lg p-4 mb-6 overflow-x-auto">
                        <pre className="text-green-400"><code>{`// Create legal hold for incident
const hold = await nuclear.holds.create({
  name: 'Hold - Incident IR-2026-01',
  caseNumber: 'IR-2026-01',
  issuingAuthority: 'Internal Legal',
  scope: {
    facilityId: 'NPP-UNIT-1',
    reactorId: 'UNIT-1'
  }
});

// Add record to hold
await nuclear.holds.addRecord(hold.hold.id, record.record.id);

console.log('Legal hold created:', hold.hold.id);
console.log('Record count:', hold.hold.recordCount);`}</code></pre>
                    </div>

                    <h3>Export Records for Discovery</h3>
                    <div className="not-prose bg-gray-900 dark:bg-black rounded-lg p-4 mb-6 overflow-x-auto">
                        <pre className="text-green-400"><code>{`// Request export (async process)
const exportHandle = await nuclear.records.export({
  facilityId: 'NPP-UNIT-1',
  query: {
    recordType: 'CYBER_SECURITY_PLAN',
    createdAfter: '2026-01-01T00:00:00Z'
  },
  format: 'jsonl',
  includeVerification: true
});

console.log('Export queued:', exportHandle.exportId);

// Poll for completion
let exportStatus = exportHandle;
while (exportStatus.status !== 'ready') {
  await new Promise(resolve => setTimeout(resolve, 5000));
  exportStatus = await nuclear.records.getExport(exportHandle.exportId);
}

console.log('Download URL:', exportStatus.download.url);
console.log('Expires:', exportStatus.download.expiresAt);`}</code></pre>
                    </div>

                    {/* Safety Guarantees */}
                    <h2 id="safety-guarantees">Safety Guarantees</h2>
                    <p>
                        The Nuclear API enforces the following guarantees server-side (not convention):
                    </p>

                    <div className="not-prose grid md:grid-cols-2 gap-6 my-8">
                        <div className="p-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                            <div className="flex items-center gap-3 mb-4">
                                <Shield className="h-6 w-6 text-green-600" />
                                <h4 className="font-semibold text-gray-900 dark:text-gray-100">
                                    Immutability
                                </h4>
                            </div>
                            <ul className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
                                <li className="flex items-start gap-2">
                                    <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                                    <span>Records cannot be modified after creation</span>
                                </li>
                                <li className="flex items-start gap-2">
                                    <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                                    <span>Database triggers prevent UPDATE operations</span>
                                </li>
                                <li className="flex items-start gap-2">
                                    <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                                    <span>Deletion blocked by retention policy</span>
                                </li>
                            </ul>
                        </div>

                        <div className="p-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                            <div className="flex items-center gap-3 mb-4">
                                <Shield className="h-6 w-6 text-green-600" />
                                <h4 className="font-semibold text-gray-900 dark:text-gray-100">
                                    Cryptographic Integrity
                                </h4>
                            </div>
                            <ul className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
                                <li className="flex items-start gap-2">
                                    <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                                    <span>SHA-256 content hashing</span>
                                </li>
                                <li className="flex items-start gap-2">
                                    <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                                    <span>Signature seal binds identity to content</span>
                                </li>
                                <li className="flex items-start gap-2">
                                    <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                                    <span>Independent verification available</span>
                                </li>
                            </ul>
                        </div>

                        <div className="p-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                            <div className="flex items-center gap-3 mb-4">
                                <Shield className="h-6 w-6 text-green-600" />
                                <h4 className="font-semibold text-gray-900 dark:text-gray-100">
                                    Attribution
                                </h4>
                            </div>
                            <ul className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
                                <li className="flex items-start gap-2">
                                    <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                                    <span>Server-assigned principal tracking</span>
                                </li>
                                <li className="flex items-start gap-2">
                                    <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                                    <span>Unforgeable attribution (JWT/session)</span>
                                </li>
                                <li className="flex items-start gap-2">
                                    <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                                    <span>Source IP and request ID captured</span>
                                </li>
                            </ul>
                        </div>

                        <div className="p-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                            <div className="flex items-center gap-3 mb-4">
                                <Shield className="h-6 w-6 text-green-600" />
                                <h4 className="font-semibold text-gray-900 dark:text-gray-100">
                                    Safety Mode
                                </h4>
                            </div>
                            <ul className="space-y-2 text-sm text-gray-700 dark:text-gray-300">
                                <li className="flex items-start gap-2">
                                    <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                                    <span>Mutations blocked during integrity failure</span>
                                </li>
                                <li className="flex items-start gap-2">
                                    <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                                    <span>HTTP 503 returned with verification URL</span>
                                </li>
                                <li className="flex items-start gap-2">
                                    <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                                    <span>Fail-safe: prevents misleading records</span>
                                </li>
                            </ul>
                        </div>
                    </div>

                    {/* Do's and Don'ts */}
                    <h2>Development Best Practices</h2>

                    <div className="not-prose grid md:grid-cols-2 gap-6 my-8">
                        <div className="p-6 bg-green-50 dark:bg-green-900/20 border border-green-200 dark:border-green-800 rounded-lg">
                            <div className="flex items-center gap-3 mb-4">
                                <CheckCircle className="h-6 w-6 text-green-600" />
                                <h4 className="font-semibold text-gray-900 dark:text-gray-100">
                                    ✅ DO
                                </h4>
                            </div>
                            <ul className="space-y-3 text-sm text-gray-700 dark:text-gray-300">
                                <li>
                                    <strong>Use environment variables</strong> for API keys
                                </li>
                                <li>
                                    <strong>Call verify()</strong> after create to confirm seal
                                </li>
                                <li>
                                    <strong>Handle SAFETY_MODE_ACTIVE</strong> errors gracefully
                                </li>
                                <li>
                                    <strong>Use clientRequestId</strong> for idempotency
                                </li>
                                <li>
                                    <strong>Log all export requests</strong> internally
                                </li>
                                <li>
                                    <strong>Treat classification</strong> as security boundary
                                </li>
                                <li>
                                    <strong>Test safety mode</strong> behavior in staging
                                </li>
                            </ul>
                        </div>

                        <div className="p-6 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg">
                            <div className="flex items-center gap-3 mb-4">
                                <XCircle className="h-6 w-6 text-red-600" />
                                <h4 className="font-semibold text-gray-900 dark:text-gray-100">
                                    ❌ DON'T
                                </h4>
                            </div>
                            <ul className="space-y-3 text-sm text-gray-700 dark:text-gray-300">
                                <li>
                                    <strong>Don't cache verification results</strong> - always call verify()
                                </li>
                                <li>
                                    <strong>Don't assume attribution</strong> - server assigns it
                                </li>
                                <li>
                                    <strong>Don't bypass safety mode</strong> in production
                                </li>
                                <li>
                                    <strong>Don't hardcode API keys</strong> in code
                                </li>
                                <li>
                                    <strong>Don't export without logging</strong> (audit requirement)
                                </li>
                                <li>
                                    <strong>Don't claim "NRC compliance"</strong> - use approved language
                                </li>
                                <li>
                                    <strong>Don't store export URLs</strong> long-term (they expire)
                                </li>
                            </ul>
                        </div>
                    </div>

                    {/* Error Handling */}
                    <h2>Error Handling</h2>
                    <p>
                        All errors follow a consistent envelope structure:
                    </p>

                    <div className="not-prose bg-gray-900 dark:bg-black rounded-lg p-4 mb-6 overflow-x-auto">
                        <pre className="text-green-400"><code>{`try {
  await nuclear.records.create({ ... });
} catch (error) {
  if (error.response?.status === 503) {
    // Safety mode active
    console.error('System integrity verification failed');
    console.error('Verify URL:', error.response.data.error.details.verifyUrl);
    // Alert compliance team
  } else if (error.response?.status === 403) {
    // Classification forbidden or scope denied
    console.error('Access denied:', error.response.data.error.message);
    console.error('Required scopes:', error.response.data.error.details.requiredScopes);
  } else if (error.response?.status === 423) {
    // Legal hold or retention locked
    console.error('Record locked:', error.response.data.error.message);
  }
}`}</code></pre>
                    </div>

                    <h3>Common Error Codes</h3>
                    <div className="not-prose overflow-x-auto">
                        <table className="min-w-full divide-y divide-gray-200 dark:divide-gray-700">
                            <thead className="bg-gray-50 dark:bg-gray-800">
                                <tr>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                        Code
                                    </th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                        HTTP
                                    </th>
                                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 dark:text-gray-400 uppercase tracking-wider">
                                        Meaning
                                    </th>
                                </tr>
                            </thead>
                            <tbody className="bg-white dark:bg-gray-900 divide-y divide-gray-200 dark:divide-gray-700">
                                <tr>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900 dark:text-gray-100">
                                        SAFETY_MODE_ACTIVE
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                                        503
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                                        Integrity verification failed, mutations blocked
                                    </td>
                                </tr>
                                <tr>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900 dark:text-gray-100">
                                        CLASSIFICATION_FORBIDDEN
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                                        403
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                                        Requested classification not permitted for API key
                                    </td>
                                </tr>
                                <tr>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900 dark:text-gray-100">
                                        LEGAL_HOLD_ACTIVE
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                                        423
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                                        Record is under legal hold, action not permitted
                                    </td>
                                </tr>
                                <tr>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm font-mono text-gray-900 dark:text-gray-100">
                                        RETENTION_LOCKED
                                    </td>
                                    <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-500 dark:text-gray-400">
                                        423
                                    </td>
                                    <td className="px-6 py-4 text-sm text-gray-500 dark:text-gray-400">
                                        Retention period not expired
                                    </td>
                                </tr>
                            </tbody>
                        </table>
                    </div>

                    {/* Next Steps */}
                    <h2>Next Steps</h2>
                    <div className="not-prose grid md:grid-cols-2 gap-6 my-8">
                        <Link href="/docs/nuclear/quickstart" className="p-6 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-orange-500 transition-colors">
                            <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                Quickstart Guide
                            </h4>
                            <p className="text-sm text-gray-600 dark:text-gray-400">
                                5-minute guide to your first compliance record
                            </p>
                        </Link>

                        <Link href="/docs/nuclear/cfr-traceability" className="p-6 border border-gray-200 dark:border-gray-700 rounded-lg hover:border-orange-500 transition-colors">
                            <h4 className="font-semibold text-gray-900 dark:text-gray-100 mb-2">
                                CFR Traceability Matrix
                            </h4>
                            <p className="text-sm text-gray-600 dark:text-gray-400">
                                Every feature mapped to 10 CFR requirements
                            </p>
                        </Link>
                    </div>
                </div>
            </div>
        </div>
    );
}
