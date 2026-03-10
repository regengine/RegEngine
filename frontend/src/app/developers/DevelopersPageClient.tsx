'use client';

import { useState } from 'react';
import { MotionConfig, motion } from 'framer-motion';
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
import Link from 'next/link';

import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Card, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

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
            <pre className="bg-[var(--re-surface-card)] text-[var(--re-text-primary)] p-4 rounded-lg overflow-x-auto text-sm border border-[var(--re-surface-border)]">
                <code data-lang={lang}>{code}</code>
            </pre>
            <Button
                size="sm"
                variant="ghost"
                className="absolute top-2 right-2 text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)]"
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
    const [installCopied, setInstallCopied] = useState(false);
    const exampleKeys = Object.keys(CODE_EXAMPLES) as Array<keyof typeof CODE_EXAMPLES>;
    const example = CODE_EXAMPLES[selectedExample];

    const focusById = (id: string) => {
        requestAnimationFrame(() => {
            const el = document.getElementById(id) as HTMLElement | null;
            el?.focus();
        });
    };

    const selectExampleTab = (exampleKey: keyof typeof CODE_EXAMPLES) => {
        setSelectedExample(exampleKey);
        setSelectedLang(0);
    };

    const selectLanguageTab = (index: number) => {
        setSelectedLang(index);
    };

    const handleInstallCopy = async () => {
        try {
            await navigator.clipboard.writeText('npm install @regengine/fsma-sdk');
            setInstallCopied(true);
            setTimeout(() => setInstallCopied(false), 2000);
        } catch {
            setInstallCopied(false);
        }
    };

    return (
        <MotionConfig reducedMotion="user">
            <div className="re-page overflow-x-hidden">
                <div className="re-noise" />

            <section className="relative z-[2] max-w-[1120px] mx-auto pt-[96px] pb-[72px] px-6">
                <div className="absolute top-[-80px] left-1/2 -translate-x-1/2 w-[640px] h-[420px] bg-[radial-gradient(ellipse,rgba(16,185,129,0.08)_0%,transparent_72%)] pointer-events-none" />
                <motion.div initial={{ opacity: 0, y: 20 }} animate={{ opacity: 1, y: 0 }} className="text-center">
                    <div className="re-badge-brand mb-7 w-fit mx-auto">
                        <span className="re-dot bg-[var(--re-brand)] animate-pulse" />
                        Developer Experience
                    </div>

                    <h1 className="text-[clamp(36px,5vw,56px)] font-bold text-[var(--re-text-primary)] leading-[1.08] mb-6 tracking-[-0.02em]">
                        The API for
                        <br />
                        <span className="text-[var(--re-brand)]">Food Traceability</span>
                    </h1>
                    <p className="text-lg text-[var(--re-text-muted)] leading-relaxed mb-8 max-w-[760px] mx-auto">
                        First FSMA 204 CTE in 5 minutes. Not 5 weeks.
                    </p>

                    <div className="flex flex-wrap items-center justify-center gap-4 text-sm text-[var(--re-text-muted)]">
                        <span className="flex items-center gap-2">
                            <Clock className="h-4 w-4 text-[var(--re-brand)]" />
                            5-min quickstart
                        </span>
                        <span className="flex items-center gap-2">
                            <Code2 className="h-4 w-4 text-[var(--re-brand)]" />
                            SDKs for Node, Python, Go
                        </span>
                        <span className="flex items-center gap-2">
                            <Shield className="h-4 w-4 text-[var(--re-brand)]" />
                            SHA-256 audit trail
                        </span>
                    </div>

                    <div className="flex flex-col sm:flex-row gap-4 justify-center mt-8">
                        <Link href="/onboarding/supplier-flow">
                            <Button size="lg" className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white">
                                Get API Key
                                <ArrowRight className="ml-2 h-4 w-4" />
                            </Button>
                        </Link>
                        <Link href="/docs">
                            <Button size="lg" variant="outline" className="border-[var(--re-surface-border)] text-[var(--re-text-primary)] hover:bg-[var(--re-surface-card)]">
                                <BookOpen className="mr-2 h-4 w-4" />
                                Read the Docs
                            </Button>
                        </Link>
                    </div>
                </motion.div>
            </section>

            <section className="relative z-[2] bg-[var(--re-surface-card)] border-y border-[var(--re-surface-border)] py-4">
                <div className="max-w-[1120px] mx-auto px-6">
                    <div className="flex items-center justify-between bg-[var(--re-surface-base)] border border-[var(--re-surface-border)] rounded-lg px-4 py-3 font-mono text-sm gap-4">
                        <div className="flex items-center gap-3 min-w-0">
                            <Terminal className="h-4 w-4 text-[var(--re-brand)] flex-shrink-0" />
                            <code className="truncate">
                                <span className="text-[var(--re-text-muted)]">$</span>{' '}
                                <span className="text-[var(--re-brand)]">npm install</span>{' '}
                                <span className="text-[var(--re-text-primary)]">@regengine/fsma-sdk</span>
                            </code>
                        </div>
                        <Button
                            size="sm"
                            variant="ghost"
                            className="text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)]"
                            onClick={handleInstallCopy}
                        >
                            {installCopied ? <Check className="h-4 w-4" /> : <Copy className="h-4 w-4" />}
                        </Button>
                    </div>
                </div>
            </section>

            <section className="relative z-[2] max-w-[1120px] mx-auto px-6 py-[80px]">
                <div className="grid lg:grid-cols-4 gap-8">
                    <div className="lg:col-span-1">
                        <h3 className="text-sm font-semibold text-[var(--re-text-muted)] uppercase tracking-wider mb-4">
                            Examples
                        </h3>
                        <nav role="tablist" aria-label="Code examples" aria-orientation="vertical" className="space-y-1">
                            {Object.entries(CODE_EXAMPLES).map(([key, ex]) => {
                                const exampleKey = key as keyof typeof CODE_EXAMPLES;
                                const index = exampleKeys.indexOf(exampleKey);

                                return (
                                    <button
                                        key={exampleKey}
                                        id={`example-tab-${exampleKey}`}
                                        role="tab"
                                        aria-selected={selectedExample === exampleKey}
                                        aria-controls={`example-panel-${exampleKey}`}
                                        tabIndex={selectedExample === exampleKey ? 0 : -1}
                                        onClick={() => selectExampleTab(exampleKey)}
                                        onKeyDown={(e) => {
                                            if (e.key === 'ArrowRight' || e.key === 'ArrowDown') {
                                                e.preventDefault();
                                                const nextKey = exampleKeys[(index + 1) % exampleKeys.length];
                                                selectExampleTab(nextKey);
                                                focusById(`example-tab-${nextKey}`);
                                            }

                                            if (e.key === 'ArrowLeft' || e.key === 'ArrowUp') {
                                                e.preventDefault();
                                                const prevKey = exampleKeys[(index - 1 + exampleKeys.length) % exampleKeys.length];
                                                selectExampleTab(prevKey);
                                                focusById(`example-tab-${prevKey}`);
                                            }

                                            if (e.key === 'Home') {
                                                e.preventDefault();
                                                const firstKey = exampleKeys[0];
                                                selectExampleTab(firstKey);
                                                focusById(`example-tab-${firstKey}`);
                                            }

                                            if (e.key === 'End') {
                                                e.preventDefault();
                                                const lastKey = exampleKeys[exampleKeys.length - 1];
                                                selectExampleTab(lastKey);
                                                focusById(`example-tab-${lastKey}`);
                                            }
                                        }}
                                        className={`w-full text-left px-3 py-2 rounded-lg transition-colors ${selectedExample === exampleKey
                                            ? 'bg-[var(--re-brand-muted)] text-[var(--re-brand)]'
                                            : 'text-[var(--re-text-muted)] hover:bg-[var(--re-surface-card)] hover:text-[var(--re-text-primary)]'
                                            }`}
                                    >
                                        {ex.title}
                                    </button>
                                );
                            })}
                        </nav>

                        <div className="mt-8 pt-8 border-t border-[var(--re-surface-border)]">
                            <h3 className="text-sm font-semibold text-[var(--re-text-muted)] uppercase tracking-wider mb-4">
                                Resources
                            </h3>
                            <nav className="space-y-2">
                                <Link href="/docs" className="flex items-center gap-2 text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)]">
                                    <BookOpen className="h-4 w-4" />
                                    Full Documentation
                                </Link>
                                <Link href="/developers/compliance-verticals" className="flex items-center gap-2 text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)]">
                                    <Shield className="h-4 w-4" />
                                    FSMA Vertical Profiles
                                </Link>
                                <Link href="/docs/api" className="flex items-center gap-2 text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)]">
                                    <Code2 className="h-4 w-4" />
                                    API Reference
                                </Link>
                                <a href="https://github.com/PetrefiedThunder" className="flex items-center gap-2 text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)]">
                                    <Terminal className="h-4 w-4" />
                                    GitHub
                                </a>
                            </nav>
                        </div>
                    </div>

                    <div className="lg:col-span-3">
                        {exampleKeys
                            .filter((exampleKey) => exampleKey !== selectedExample)
                            .map((exampleKey) => (
                                <div
                                    key={`example-panel-placeholder-${exampleKey}`}
                                    role="tabpanel"
                                    id={`example-panel-${exampleKey}`}
                                    aria-labelledby={`example-tab-${exampleKey}`}
                                    hidden
                                />
                            ))}
                        <motion.div
                            key={selectedExample}
                            initial={{ opacity: 0, x: 20 }}
                            animate={{ opacity: 1, x: 0 }}
                            role="tabpanel"
                            id={`example-panel-${selectedExample}`}
                            aria-labelledby={`example-tab-${selectedExample}`}
                            tabIndex={0}
                        >
                            <div className="mb-6">
                                <h2 className="text-2xl font-bold mb-2 text-[var(--re-text-primary)]">{example.title}</h2>
                                <p className="text-[var(--re-text-muted)]">{example.description}</p>
                            </div>

                            <div className="mb-4">
                                <div role="tablist" aria-label="Code languages" className="flex gap-2">
                                    {example.tabs.map((tab, i) => (
                                        <button
                                            key={tab.lang}
                                            id={`code-tab-${selectedExample}-${tab.lang}`}
                                            role="tab"
                                            aria-selected={selectedLang === i}
                                            aria-controls={`code-panel-${selectedExample}-${tab.lang}`}
                                            tabIndex={selectedLang === i ? 0 : -1}
                                            onClick={() => selectLanguageTab(i)}
                                            onKeyDown={(e) => {
                                                if (e.key === 'ArrowRight') {
                                                    e.preventDefault();
                                                    const nextIndex = (i + 1) % example.tabs.length;
                                                    selectLanguageTab(nextIndex);
                                                    focusById(`code-tab-${selectedExample}-${example.tabs[nextIndex].lang}`);
                                                }

                                                if (e.key === 'ArrowLeft') {
                                                    e.preventDefault();
                                                    const prevIndex = (i - 1 + example.tabs.length) % example.tabs.length;
                                                    selectLanguageTab(prevIndex);
                                                    focusById(`code-tab-${selectedExample}-${example.tabs[prevIndex].lang}`);
                                                }

                                                if (e.key === 'Home') {
                                                    e.preventDefault();
                                                    selectLanguageTab(0);
                                                    focusById(`code-tab-${selectedExample}-${example.tabs[0].lang}`);
                                                }

                                                if (e.key === 'End') {
                                                    e.preventDefault();
                                                    const lastIndex = example.tabs.length - 1;
                                                    selectLanguageTab(lastIndex);
                                                    focusById(`code-tab-${selectedExample}-${example.tabs[lastIndex].lang}`);
                                                }
                                            }}
                                            className={`px-3 py-1 rounded text-sm font-medium transition-colors ${selectedLang === i
                                                ? 'bg-[var(--re-brand-muted)] text-[var(--re-brand)]'
                                                : 'bg-[var(--re-surface-card)] text-[var(--re-text-muted)] hover:text-[var(--re-text-primary)]'
                                                }`}
                                        >
                                            {tab.label}
                                        </button>
                                    ))}
                                </div>
                            </div>

                            {example.tabs.map((tab, i) => (
                                <div
                                    key={tab.lang}
                                    role="tabpanel"
                                    id={`code-panel-${selectedExample}-${tab.lang}`}
                                    aria-labelledby={`code-tab-${selectedExample}-${tab.lang}`}
                                    hidden={selectedLang !== i}
                                    tabIndex={0}
                                >
                                    {selectedLang === i ? <CodeBlock code={tab.code} lang={tab.lang} /> : null}
                                </div>
                            ))}

                            <div className="mt-4 flex gap-3">
                                <Link href="/demo/mock-recall">
                                    <Button className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white">
                                        <Play className="mr-2 h-4 w-4" />
                                        Run in Playground
                                    </Button>
                                </Link>
                                <Link href="/docs">
                                    <Button variant="outline" className="border-[var(--re-surface-border)] text-[var(--re-text-primary)] hover:bg-[var(--re-surface-card)]">
                                        View Full Example
                                    </Button>
                                </Link>
                            </div>
                        </motion.div>
                    </div>
                </div>
            </section>

            <section className="relative z-[2] border-t border-[var(--re-surface-border)] bg-[var(--re-surface-card)] py-[72px] px-6">
                <div className="max-w-[1120px] mx-auto">
                    <h2 className="text-2xl font-bold text-center mb-12 text-[var(--re-text-primary)]">
                        Why Developers Choose RegEngine
                    </h2>
                    <div className="grid md:grid-cols-3 gap-8">
                        <Card className="bg-[var(--re-surface-base)] border-[var(--re-surface-border)]">
                            <CardHeader>
                                <Zap className="h-8 w-8 text-[var(--re-brand)] mb-2" />
                                <CardTitle>5-Minute Quickstart</CardTitle>
                                <CardDescription className="text-[var(--re-text-muted)]">
                                    npm install, add your API key, and you are recording CTEs.
                                    No weeks of onboarding calls.
                                </CardDescription>
                            </CardHeader>
                        </Card>
                        <Card className="bg-[var(--re-surface-base)] border-[var(--re-surface-border)]">
                            <CardHeader>
                                <Code2 className="h-8 w-8 text-[var(--re-brand)] mb-2" />
                                <CardTitle>First-Class SDKs</CardTitle>
                                <CardDescription className="text-[var(--re-text-muted)]">
                                    Type-safe SDKs for Node.js, Python, and Go.
                                    No raw HTTP requests needed.
                                </CardDescription>
                            </CardHeader>
                        </Card>
                        <Card className="bg-[var(--re-surface-base)] border-[var(--re-surface-border)]">
                            <CardHeader>
                                <Terminal className="h-8 w-8 text-[var(--re-brand)] mb-2" />
                                <CardTitle>Interactive Playground</CardTitle>
                                <CardDescription className="text-[var(--re-text-muted)]">
                                    Test API calls in your browser before writing code.
                                    See real responses instantly.
                                </CardDescription>
                            </CardHeader>
                        </Card>
                    </div>
                </div>
            </section>

            <section className="relative z-[2] max-w-[1120px] mx-auto py-[88px] px-6">
                <div className="rounded-2xl p-9 md:p-12 bg-gradient-to-r from-[rgba(16,185,129,0.2)] to-[rgba(59,130,246,0.18)] border border-[var(--re-surface-border)]">
                    <h3 className="text-[28px] font-bold text-[var(--re-text-primary)] mb-3">
                        Ready to build?
                    </h3>
                    <p className="text-[var(--re-text-secondary)] leading-relaxed max-w-[760px]">
                        Get your API key and send your first CTE in under 5 minutes.
                    </p>
                    <p className="text-sm text-[var(--re-text-muted)] mt-3">
                        Start with a free 14-day trial.{' '}
                        <Link href="/pricing" className="font-semibold text-[var(--re-brand)] hover:underline">
                            See all plans.
                        </Link>
                    </p>
                    <div className="flex flex-col sm:flex-row gap-4 mt-8">
                        <Link href="/onboarding/supplier-flow">
                            <Button size="lg" className="bg-[var(--re-brand)] hover:bg-[var(--re-brand-dark)] text-white">
                                Get Free API Key
                                <ArrowRight className="ml-2 h-4 w-4" />
                            </Button>
                        </Link>
                        <Link href="/pricing">
                            <Button size="lg" variant="outline" className="border-[var(--re-surface-border)] text-[var(--re-text-primary)] hover:bg-[var(--re-surface-card)]">
                                View Pricing
                            </Button>
                        </Link>
                    </div>
                </div>
            </section>
            </div>
        </MotionConfig>
    );
}
