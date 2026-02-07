'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import {
    Code2,
    Play,
    Copy,
    Check,
    Terminal,
    ArrowRight,
    Zap,
    Clock,
    Shield,
    BookOpen,
} from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import Link from 'next/link';

const CODE_EXAMPLES = {
    quickstart: {
        title: 'Quickstart (5 minutes)',
        description: 'Send your first Critical Tracking Event',
        tabs: [
            {
                lang: 'javascript',
                label: 'Node.js',
                code: `import { RegEngine } from '@regengine/fsma-sdk';

// Initialize with your API key
const rg = new RegEngine('rge_your_api_key_here');

// Record a receiving event
const event = await rg.events.create({
  type: 'RECEIVING',
  tlc: 'LOT-2024-001',
  product: {
    description: 'Fresh Romaine Lettuce',
    gtin: '00614141000012'
  },
  quantity: { value: 500, unit: 'cases' },
  location: { gln: '0614141000012', name: 'Main Warehouse' },
  timestamp: new Date().toISOString(),
  kdes: {
    supplier_lot: 'SUPP-TF-2024-001',
    po_number: 'PO-12345',
    carrier: 'FastFreight Logistics'
  }
});

console.log('Event recorded:', event.id);`,
            },
            {
                lang: 'python',
                label: 'Python',
                code: `from regengine import RegEngine

# Initialize with your API key
rg = RegEngine(api_key='rge_your_api_key_here')

# Record a receiving event
event = rg.events.create(
    event_type='RECEIVING',
    tlc='LOT-2024-001',
    product={
        'description': 'Fresh Romaine Lettuce',
        'gtin': '00614141000012'
    },
    quantity={'value': 500, 'unit': 'cases'},
    location={'gln': '0614141000012', 'name': 'Main Warehouse'},
    kdes={
        'supplier_lot': 'SUPP-TF-2024-001',
        'po_number': 'PO-12345',
        'carrier': 'FastFreight Logistics'
    }
)

print(f'Event recorded: {event.id}')`,
            },
            {
                lang: 'curl',
                label: 'cURL',
                code: `curl -X POST https://api.regengine.co/v1/fsma/events \\
  -H "X-RegEngine-API-Key: rge_your_api_key_here" \\
  -H "Content-Type: application/json" \\
  -d '{
    "type": "RECEIVING",
    "tlc": "LOT-2024-001",
    "product": {
      "description": "Fresh Romaine Lettuce",
      "gtin": "00614141000012"
    },
    "quantity": {"value": 500, "unit": "cases"},
    "location": {"gln": "0614141000012", "name": "Main Warehouse"},
    "kdes": {
      "supplier_lot": "SUPP-TF-2024-001",
      "po_number": "PO-12345",
      "carrier": "FastFreight Logistics"
    }
  }'`,
            },
        ],
    },
    trace: {
        title: 'Trace a Lot',
        description: 'Follow a lot through your supply chain',
        tabs: [
            {
                lang: 'javascript',
                label: 'Node.js',
                code: `// Forward trace: Where did this lot go?
const forwardTrace = await rg.trace.forward('LOT-2024-001');
console.log(\`Found \${forwardTrace.events.length} downstream events\`);

// Backward trace: Where did this lot come from?
const backwardTrace = await rg.trace.backward('LOT-2024-001');
console.log(\`Found \${backwardTrace.events.length} upstream events\`);

// Full supply chain visualization
const timeline = await rg.trace.timeline('LOT-2024-001');
timeline.events.forEach(event => {
  console.log(\`\${event.timestamp}: \${event.type} at \${event.location.name}\`);
});`,
            },
            {
                lang: 'python',
                label: 'Python',
                code: `# Forward trace: Where did this lot go?
forward_trace = rg.trace.forward('LOT-2024-001')
print(f'Found {len(forward_trace.events)} downstream events')

# Backward trace: Where did this lot come from?
backward_trace = rg.trace.backward('LOT-2024-001')
print(f'Found {len(backward_trace.events)} upstream events')

# Full supply chain visualization
timeline = rg.trace.timeline('LOT-2024-001')
for event in timeline.events:
    print(f'{event.timestamp}: {event.type} at {event.location.name}')`,
            },
        ],
    },
    recall: {
        title: 'Mock Recall Drill',
        description: 'Test your 24-hour FDA response capability',
        tabs: [
            {
                lang: 'javascript',
                label: 'Node.js',
                code: `// Start a mock recall drill
const drill = await rg.recall.startDrill({
  tlc: 'LOT-2024-001',
  direction: 'FORWARD', // or 'BACKWARD'
  targetTimeHours: 24,
});

// Check drill progress
const status = await rg.recall.getDrill(drill.id);
console.log(\`Drill status: \${status.state}\`);
console.log(\`Affected facilities: \${status.impactedFacilities.length}\`);
console.log(\`Time elapsed: \${status.elapsedHours} hours\`);

// Export FDA-ready report
const report = await rg.recall.exportReport(drill.id, {
  format: 'FDA_204',
});
console.log('Report ready:', report.downloadUrl);`,
            },
        ],
    },
    gaps: {
        title: 'Find Compliance Gaps',
        description: 'Identify missing KDEs and broken chains',
        tabs: [
            {
                lang: 'javascript',
                label: 'Node.js',
                code: `// Find events with missing Key Data Elements
const gaps = await rg.compliance.findGaps({
  dateRange: { start: '2024-01-01', end: '2024-12-31' },
  severity: 'ALL', // or 'HIGH', 'MEDIUM', 'LOW'
});

gaps.forEach(gap => {
  console.log(\`Event \${gap.eventId}: Missing \${gap.missingKdes.join(', ')}\`);
});

// Find orphaned lots (no downstream events)
const orphans = await rg.compliance.findOrphans({
  staleAfterDays: 30,
});

console.log(\`Found \${orphans.length} orphaned lots\`);

// Get overall compliance score
const score = await rg.compliance.getScore();
console.log(\`Compliance score: \${score.overall}%\`);`,
            },
        ],
    },
};

function CodeBlock({ code, lang }: { code: string; lang: string }) {
    const [copied, setCopied] = useState(false);

    const handleCopy = async () => {
        await navigator.clipboard.writeText(code);
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
    };

    return (
        <div className="relative">
            <pre className="bg-gray-900 text-gray-100 p-4 rounded-lg overflow-x-auto text-sm">
                <code>{code}</code>
            </pre>
            <Button
                size="sm"
                variant="ghost"
                className="absolute top-2 right-2 text-gray-400 hover:text-white"
                onClick={handleCopy}
            >
                {copied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
            </Button>
        </div>
    );
}

export default function DevelopersPage() {
    const [selectedExample, setSelectedExample] = useState<keyof typeof CODE_EXAMPLES>('quickstart');
    const [selectedLang, setSelectedLang] = useState(0);

    const example = CODE_EXAMPLES[selectedExample];

    return (
        <div className="min-h-screen bg-gray-950 text-gray-100">            {/* Hero */}
            <div className="border-b border-gray-800 py-16 px-4">
                <div className="max-w-4xl mx-auto text-center">
                    <motion.div
                        initial={{ opacity: 0, y: 20 }}
                        animate={{ opacity: 1, y: 0 }}
                    >
                        <Badge className="mb-4 bg-emerald-500/20 text-emerald-400 border-emerald-500/50">
                            Developer Experience
                        </Badge>
                        <h1 className="text-4xl md:text-5xl font-bold mb-4">
                            The API for<br />
                            <span className="text-emerald-400">Food Traceability</span>
                        </h1>
                        <p className="text-xl text-gray-400 mb-8">
                            First FSMA 204 CTE in 5 minutes. Not 5 weeks.
                        </p>

                        <div className="flex flex-wrap items-center justify-center gap-4 text-sm text-gray-500">
                            <span className="flex items-center gap-2">
                                <Clock className="h-4 w-4 text-emerald-400" />
                                5-min quickstart
                            </span>
                            <span className="flex items-center gap-2">
                                <Code2 className="h-4 w-4 text-emerald-400" />
                                SDKs for Node, Python, Go
                            </span>
                            <span className="flex items-center gap-2">
                                <Shield className="h-4 w-4 text-emerald-400" />
                                SHA-256 audit trail
                            </span>
                        </div>

                        <div className="flex flex-col sm:flex-row gap-4 justify-center mt-8">
                            <Link href="/onboarding">
                                <Button size="lg" className="bg-emerald-600 hover:bg-emerald-700">
                                    Get API Key
                                    <ArrowRight className="ml-2 h-4 w-4" />
                                </Button>
                            </Link>
                            <Link href="/docs">
                                <Button size="lg" variant="outline" className="border-gray-700 text-gray-300 hover:bg-gray-800">
                                    <BookOpen className="mr-2 h-4 w-4" />
                                    Read the Docs
                                </Button>
                            </Link>
                        </div>
                    </motion.div>
                </div>
            </div>

            {/* Install Banner */}
            <div className="bg-gray-900 border-b border-gray-800 py-4">
                <div className="max-w-4xl mx-auto px-4">
                    <div className="flex items-center justify-between bg-gray-950 rounded-lg px-4 py-3 font-mono text-sm">
                        <div className="flex items-center gap-3">
                            <Terminal className="h-4 w-4 text-emerald-400" />
                            <code>
                                <span className="text-gray-500">$</span>{' '}
                                <span className="text-emerald-400">npm install</span>{' '}
                                <span className="text-white">@regengine/fsma-sdk</span>
                            </code>
                        </div>
                        <Button size="sm" variant="ghost" className="text-gray-400 hover:text-white">
                            <Copy className="h-4 w-4" />
                        </Button>
                    </div>
                </div>
            </div>

            {/* Code Examples */}
            <div className="max-w-6xl mx-auto px-4 py-16">
                <div className="grid lg:grid-cols-4 gap-8">
                    {/* Sidebar */}
                    <div className="lg:col-span-1">
                        <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
                            Examples
                        </h3>
                        <nav className="space-y-1">
                            {Object.entries(CODE_EXAMPLES).map(([key, ex]) => (
                                <button
                                    key={key}
                                    onClick={() => {
                                        setSelectedExample(key as keyof typeof CODE_EXAMPLES);
                                        setSelectedLang(0);
                                    }}
                                    className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${selectedExample === key
                                        ? 'bg-emerald-500/20 text-emerald-400'
                                        : 'text-gray-400 hover:bg-gray-800 hover:text-white'
                                        }`}
                                >
                                    {ex.title}
                                </button>
                            ))}
                        </nav>

                        <div className="mt-8 pt-8 border-t border-gray-800">
                            <h3 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
                                Resources
                            </h3>
                            <nav className="space-y-2">
                                <a href="/docs" className="flex items-center gap-2 text-gray-400 hover:text-white">
                                    <BookOpen className="h-4 w-4" />
                                    Full Documentation
                                </a>
                                <Link href="/developers/compliance-verticals" className="flex items-center gap-2 text-gray-400 hover:text-white">
                                    <Shield className="h-4 w-4" />
                                    Compliance Frameworks
                                </Link>
                                <a href="/docs/api" className="flex items-center gap-2 text-gray-400 hover:text-white">
                                    <Code2 className="h-4 w-4" />
                                    API Reference
                                </a>
                                <a href="https://github.com/regengine" className="flex items-center gap-2 text-gray-400 hover:text-white">
                                    <Terminal className="h-4 w-4" />
                                    GitHub
                                </a>
                            </nav>
                        </div>
                    </div>

                    {/* Main Content */}
                    <div className="lg:col-span-3">
                        <motion.div
                            key={selectedExample}
                            initial={{ opacity: 0, x: 20 }}
                            animate={{ opacity: 1, x: 0 }}
                        >
                            <div className="mb-6">
                                <h2 className="text-2xl font-bold mb-2">{example.title}</h2>
                                <p className="text-gray-400">{example.description}</p>
                            </div>

                            {/* Language Tabs */}
                            <div className="mb-4">
                                <div className="flex gap-2">
                                    {example.tabs.map((tab, i) => (
                                        <button
                                            key={tab.lang}
                                            onClick={() => setSelectedLang(i)}
                                            className={`px-3 py-1 rounded text-sm font-medium transition-colors ${selectedLang === i
                                                ? 'bg-emerald-500/20 text-emerald-400'
                                                : 'bg-gray-800 text-gray-400 hover:text-white'
                                                }`}
                                        >
                                            {tab.label}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {/* Code Block */}
                            <CodeBlock
                                code={example.tabs[selectedLang]?.code || ''}
                                lang={example.tabs[selectedLang]?.lang || 'javascript'}
                            />

                            {/* Try It Button */}
                            <div className="mt-4 flex gap-3">
                                <Link href="/demo/mock-recall">
                                    <Button className="bg-emerald-600 hover:bg-emerald-700">
                                        <Play className="mr-2 h-4 w-4" />
                                        Run in Playground
                                    </Button>
                                </Link>
                                <Link href="/docs">
                                    <Button variant="outline" className="border-gray-700 text-gray-300 hover:bg-gray-800">
                                        View Full Example
                                    </Button>
                                </Link>
                            </div>
                        </motion.div>
                    </div>
                </div>
            </div>

            {/* Features Grid */}
            <div className="border-t border-gray-800 bg-gray-900 py-16 px-4">
                <div className="max-w-6xl mx-auto">
                    <h2 className="text-2xl font-bold text-center mb-12">
                        Why Developers Choose RegEngine
                    </h2>
                    <div className="grid md:grid-cols-3 gap-8">
                        <Card className="bg-gray-950 border-gray-800">
                            <CardHeader>
                                <Zap className="h-8 w-8 text-emerald-400 mb-2" />
                                <CardTitle>5-Minute Quickstart</CardTitle>
                                <CardDescription className="text-gray-400">
                                    npm install, add your API key, and you're recording CTEs.
                                    No weeks of onboarding calls.
                                </CardDescription>
                            </CardHeader>
                        </Card>
                        <Card className="bg-gray-950 border-gray-800">
                            <CardHeader>
                                <Code2 className="h-8 w-8 text-emerald-400 mb-2" />
                                <CardTitle>First-Class SDKs</CardTitle>
                                <CardDescription className="text-gray-400">
                                    Type-safe SDKs for Node.js, Python, and Go.
                                    No raw HTTP requests needed.
                                </CardDescription>
                            </CardHeader>
                        </Card>
                        <Card className="bg-gray-950 border-gray-800">
                            <CardHeader>
                                <Terminal className="h-8 w-8 text-emerald-400 mb-2" />
                                <CardTitle>Interactive Playground</CardTitle>
                                <CardDescription className="text-gray-400">
                                    Test API calls in your browser before writing code.
                                    See real responses instantly.
                                </CardDescription>
                            </CardHeader>
                        </Card>
                    </div>
                </div>
            </div>

            {/* CTA */}
            <div className="py-16 px-4 text-center">
                <h2 className="text-2xl font-bold mb-4">
                    Ready to build?
                </h2>
                <p className="text-gray-400 mb-8">
                    Get your API key and send your first CTE in under 5 minutes.
                </p>
                <div className="flex flex-col sm:flex-row gap-4 justify-center">
                    <Link href="/onboarding">
                        <Button size="lg" className="bg-emerald-600 hover:bg-emerald-700">
                            Get Free API Key
                            <ArrowRight className="ml-2 h-4 w-4" />
                        </Button>
                    </Link>
                    <Link href="/pricing">
                        <Button size="lg" variant="outline" className="border-gray-700 text-gray-300 hover:bg-gray-800">
                            View Pricing
                        </Button>
                    </Link>
                </div>
            </div>
        </div>
    );
}
