'use client';

import { useState, useEffect, useCallback } from 'react';
import { ChevronDown, Keyboard } from 'lucide-react';
import { T } from '../_data';
import { CopyButton } from './copy-button';

/* ── Syntax highlighting (zero-dep) ── */
function highlightSyntax(code: string, lang: 'curl' | 'python' | 'node'): React.ReactNode[] {
    const lines = code.split('\n');
    return lines.map((line, i) => {
        if (line.trimStart().startsWith('#') || line.trimStart().startsWith('//')) {
            return <span key={i}><span style={{ color: 'rgba(255,255,255,0.25)', fontStyle: 'italic' }}>{line}</span>{'\n'}</span>;
        }
        const patterns: [RegExp, string][] = lang === 'curl' ? [
            [/\b(curl)\b/g, '#c792ea'], [/-[HXd]\b/g, '#82aaff'],
            [/"[^"]*"/g, '#c3e88d'], [/https?:\/\/\S+/g, '#89ddff'],
        ] : lang === 'python' ? [
            [/\b(import|from|as|print|def|return|if|else|for|in)\b/g, '#c792ea'],
            [/\b(requests|resp|score|sim)\b/g, '#82aaff'],
            [/(f?"[^"]*"|'[^']*')/g, '#c3e88d'], [/\b\d+\b/g, '#f78c6c'],
        ] : [
            [/\b(const|let|var|await|async|import|from|export)\b/g, '#c792ea'],
            [/\b(fetch|console|JSON)\b/g, '#82aaff'],
            [/("[^"]*"|'[^']*'|`[^`]*`)/g, '#c3e88d'], [/\b\d+\b/g, '#f78c6c'],
        ];
        let segments: { text: string; color?: string }[] = [{ text: line }];
        for (const [regex, color] of patterns) {
            const next: { text: string; color?: string }[] = [];
            for (const seg of segments) {
                if (seg.color) { next.push(seg); continue; }
                let last = 0;
                const r = new RegExp(regex.source, regex.flags);
                let m: RegExpExecArray | null;
                while ((m = r.exec(seg.text)) !== null) {
                    if (m.index > last) next.push({ text: seg.text.slice(last, m.index) });
                    next.push({ text: m[0], color });
                    last = m.index + m[0].length;
                }
                if (last < seg.text.length) next.push({ text: seg.text.slice(last) });
            }
            segments = next;
        }
        return (
            <span key={i}>
                {segments.map((s, j) => s.color
                    ? <span key={j} style={{ color: s.color }}>{s.text}</span>
                    : <span key={j}>{s.text}</span>
                )}{'\n'}
            </span>
        );
    });
}

/* ── JSON highlighting ── */
function highlightJSON(json: string): React.ReactNode[] {
    return json.split('\n').map((line, i) => {
        const parts: React.ReactNode[] = [];
        let remaining = line;
        let key = 0;
        remaining = line.replace(/"([^"]+)":/g, (_, k) => `__KEY__${k}__ENDKEY__:`);
        remaining = remaining.replace(/: "([^"]+)"/g, ': __STR__$1__ENDSTR__');
        remaining = remaining.replace(/\b(true|false|null)\b/g, '__BOOL__$1__ENDBOOL__');
        remaining = remaining.replace(/:\s*(\d+\.?\d*)/g, ': __NUM__$1__ENDNUM__');
        const tokens = remaining.split(/(__KEY__|__ENDKEY__|__STR__|__ENDSTR__|__BOOL__|__ENDBOOL__|__NUM__|__ENDNUM__)/);
        let mode = 'normal';
        for (const token of tokens) {
            if (token === '__KEY__') { mode = 'key'; continue; }
            if (token === '__ENDKEY__') { mode = 'normal'; continue; }
            if (token === '__STR__') { mode = 'str'; continue; }
            if (token === '__ENDSTR__') { mode = 'normal'; continue; }
            if (token === '__BOOL__') { mode = 'bool'; continue; }
            if (token === '__ENDBOOL__') { mode = 'normal'; continue; }
            if (token === '__NUM__') { mode = 'num'; continue; }
            if (token === '__ENDNUM__') { mode = 'normal'; continue; }
            if (!token) continue;
            const color = mode === 'key' ? '#82aaff' : mode === 'str' ? '#c3e88d' : mode === 'bool' ? '#c792ea' : mode === 'num' ? '#f78c6c' : undefined;
            parts.push(color
                ? <span key={key++} style={{ color }}>{mode === 'key' ? `"${token}"` : mode === 'str' ? `"${token}"` : token}</span>
                : <span key={key++}>{token}</span>
            );
        }
        return <span key={i}>{parts}{'\n'}</span>;
    });
}

/* ── CodeBlock with language tabs + response preview ── */
function CodeBlock({ examples, response }: { examples: { curl: string; python: string; node: string }; response: string }) {
    const [lang, setLang] = useState<'curl' | 'python' | 'node'>('curl');
    const [showResponse, setShowResponse] = useState(false);
    const labels: Record<string, string> = { curl: 'cURL', python: 'Python', node: 'Node.js' };
    return (
        <div style={{ animation: 're-fade-in .3s ease-out' }}>
            <div style={{ position: 'relative', borderRadius: '10px 10px 0 0', overflow: 'hidden', border: `1px solid ${T.border}`, borderBottom: 'none' }}>
                <div style={{ display: 'flex', borderBottom: `1px solid ${T.border}`, background: 'rgba(0,0,0,0.25)' }}>
                    {(Object.keys(labels) as Array<'curl' | 'python' | 'node'>).map((k) => (
                        <button key={k} onClick={() => setLang(k)} className="re-code-tab" style={{
                            padding: '9px 18px', fontSize: 12, fontWeight: 600, fontFamily: T.mono,
                            background: lang === k ? 'rgba(255,255,255,0.04)' : 'transparent',
                            color: lang === k ? T.accent : T.textMuted,
                            border: 'none', borderBottom: lang === k ? `2px solid ${T.accent}` : '2px solid transparent',
                            cursor: 'pointer',
                        }}>{labels[k]}</button>
                    ))}
                    <div style={{ flex: 1 }} />
                    <span style={{ padding: '9px 14px', fontSize: 11, color: 'rgba(255,255,255,0.18)', fontFamily: T.mono }}>request</span>
                </div>
                <div style={{ position: 'relative' }}>
                    <CopyButton text={examples[lang]} />
                    <pre style={{ background: 'rgba(0,0,0,0.4)', padding: '18px 18px 18px 22px', overflow: 'auto', fontSize: 12, lineHeight: 1.75, fontFamily: T.mono, color: T.textMuted, margin: 0, maxHeight: 340 }}>
                        <code>{highlightSyntax(examples[lang], lang)}</code>
                    </pre>
                </div>
            </div>
            {/* Response toggle */}
            <div style={{ borderRadius: '0 0 10px 10px', overflow: 'hidden', border: `1px solid ${T.border}` }}>
                <button onClick={() => setShowResponse(!showResponse)} style={{
                    width: '100%', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '10px 18px', background: 'rgba(16,185,129,0.04)', border: 'none',
                    cursor: 'pointer', fontSize: 12, fontFamily: T.mono, color: T.accent, fontWeight: 600,
                }}>
                    <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                        <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981' }} />
                        200 OK — Response
                    </span>
                    <ChevronDown style={{ width: 14, height: 14, transition: 'transform .2s', transform: showResponse ? 'rotate(180deg)' : 'rotate(0)' }} />
                </button>
                {showResponse && (
                    <div style={{ position: 'relative' }}>
                        <CopyButton text={response} />
                        <pre style={{ background: 'rgba(0,0,0,0.35)', padding: '16px 18px 16px 22px', overflow: 'auto', fontSize: 12, lineHeight: 1.65, fontFamily: T.mono, margin: 0, maxHeight: 260, color: T.textMuted }}>
                            <code>{highlightJSON(response)}</code>
                        </pre>
                    </div>
                )}
            </div>
        </div>
    );
}

/* ── Example data ── */
const EXAMPLES: Record<string, { curl: string; python: string; node: string; response: string }> = {
    'Record CTE': {
        curl: `curl -X POST https://api.regengine.co/v1/webhooks/ingest \\
  -H "X-RegEngine-API-Key: rge_live_abc123" \\
  -H "Content-Type: application/json" \\
  -d '{
    "events": [{
      "event_type": "receiving",
      "tlc": "LOT-2024-001",
      "product_description": "Fresh Romaine Lettuce",
      "quantity": 500,
      "unit": "cases",
      "location_name": "Main Warehouse",
      "timestamp": "2025-03-10T14:30:00Z",
      "kdes": {
        "supplier_lot": "SUPP-TF-2024-001",
        "po_number": "PO-12345"
      }
    }]
  }'`,
        python: `import requests

resp = requests.post(
    "https://api.regengine.co/v1/webhooks/ingest",
    headers={"X-RegEngine-API-Key": "rge_live_abc123"},
    json={"events": [{
        "event_type": "receiving",
        "tlc": "LOT-2024-001",
        "product_description": "Fresh Romaine Lettuce",
        "quantity": 500, "unit": "cases",
        "location_name": "Main Warehouse",
        "timestamp": "2025-03-10T14:30:00Z",
        "kdes": {"supplier_lot": "SUPP-TF-2024-001"}
    }]}
)
print(resp.json())`,
        node: `const resp = await fetch(
  "https://api.regengine.co/v1/webhooks/ingest",
  {
    method: "POST",
    headers: {
      "X-RegEngine-API-Key": "rge_live_abc123",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      events: [{
        event_type: "receiving",
        tlc: "LOT-2024-001",
        product_description: "Fresh Romaine Lettuce",
        quantity: 500, unit: "cases",
        location_name: "Main Warehouse",
        timestamp: "2025-03-10T14:30:00Z",
        kdes: { supplier_lot: "SUPP-TF-2024-001" },
      }],
    }),
  }
);
const data = await resp.json();`,
        response: `{
  "status": "ok",
  "ingested": 1,
  "chain_hash": "sha256:a1b2c3d4e5f6...",
  "event_ids": ["evt_9f8e7d6c5b4a"],
  "timestamp": "2025-03-10T14:30:01Z"
}`,
    },
    'Compliance Score': {
        curl: `curl https://api.regengine.co/v1/compliance/score/tenant_abc \\
  -H "X-RegEngine-API-Key: rge_live_abc123"`,
        python: `import requests

resp = requests.get(
    "https://api.regengine.co/v1/compliance/score/tenant_abc",
    headers={"X-RegEngine-API-Key": "rge_live_abc123"}
)
score = resp.json()
print(f"Grade: {score['grade']} ({score['overall_score']}%)")`,
        node: `const resp = await fetch(
  "https://api.regengine.co/v1/compliance/score/tenant_abc",
  { headers: { "X-RegEngine-API-Key": "rge_live_abc123" } }
);
const score = await resp.json();
console.log(\`Grade: \${score.grade} (\${score.overall_score}%)\`);`,
        response: `{
  "tenant_id": "tenant_abc",
  "overall_score": 87,
  "grade": "B+",
  "breakdown": {
    "chain_integrity": { "score": 95, "weight": 0.25 },
    "kde_completeness": { "score": 82, "weight": 0.20 },
    "cte_completeness": { "score": 88, "weight": 0.20 }
  },
  "next_actions": [
    { "priority": "high", "action": "Add supplier GLN" }
  ]
}`,
    },
    'Recall Drill': {
        curl: `curl -X POST https://api.regengine.co/v1/recall-simulations/run \\
  -H "X-RegEngine-API-Key: rge_live_abc123" \\
  -H "Content-Type: application/json" \\
  -d '{
    "tenant_id": "tenant_abc",
    "tlc": "LOT-2024-001",
    "reason": "Quarterly drill"
  }'`,
        python: `import requests

resp = requests.post(
    "https://api.regengine.co/v1/recall-simulations/run",
    headers={"X-RegEngine-API-Key": "rge_live_abc123"},
    json={
        "tenant_id": "tenant_abc",
        "tlc": "LOT-2024-001",
        "reason": "Quarterly drill"
    }
)
sim = resp.json()
print(f"Traced {sim['lots_affected']} lots in {sim['response_time_hours']}h")`,
        node: `const resp = await fetch(
  "https://api.regengine.co/v1/recall-simulations/run",
  {
    method: "POST",
    headers: {
      "X-RegEngine-API-Key": "rge_live_abc123",
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      tenant_id: "tenant_abc",
      tlc: "LOT-2024-001",
      reason: "Quarterly drill",
    }),
  }
);
const sim = await resp.json();`,
        response: `{
  "simulation_id": "sim_7a8b9c0d",
  "status": "complete",
  "lots_affected": 12,
  "suppliers_traced": 3,
  "facilities_involved": 5,
  "response_time_hours": 4.2,
  "sla_target_hours": 24,
  "sla_met": true,
  "fda_package_ready": true
}`,
    },
};

/* ── Exported section component ── */
export function CodeExamples() {
    const [activeExample, setActiveExample] = useState<string>('Record CTE');

    /* Keyboard shortcuts: 1/2/3 to switch examples */
    useEffect(() => {
        const keys = Object.keys(EXAMPLES);
        const handler = (e: KeyboardEvent) => {
            if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
            const idx = parseInt(e.key) - 1;
            if (idx >= 0 && idx < keys.length) setActiveExample(keys[idx]);
        };
        window.addEventListener('keydown', handler);
        return () => window.removeEventListener('keydown', handler);
    }, []);

    return (
        <section id="examples" style={{ position: 'relative', zIndex: 2, borderTop: `1px solid ${T.border}`, background: 'rgba(255,255,255,0.008)', scrollMarginTop: 60 }}>
            <div style={{ maxWidth: 880, margin: '0 auto', padding: '64px 24px' }}>
                <div style={{ display: 'flex', alignItems: 'baseline', justifyContent: 'space-between', flexWrap: 'wrap', gap: 12, marginBottom: 8 }}>
                    <h2 style={{ fontSize: 26, fontWeight: 700, color: T.heading, margin: 0 }}>Try it now</h2>
                    <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                        <span className="re-nav-shortcuts" style={{ display: 'flex', alignItems: 'center', gap: 4, fontSize: 11, color: 'rgba(255,255,255,0.2)' }}>
                            <Keyboard style={{ width: 12, height: 12 }} /> Press <kbd className="re-kbd">1</kbd><kbd className="re-kbd">2</kbd><kbd className="re-kbd">3</kbd> to switch
                        </span>
                        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
                            <span style={{ width: 6, height: 6, borderRadius: '50%', background: '#10b981', animation: 're-pulse-dot 2s ease-in-out infinite' }} />
                            <span style={{ fontSize: 12, color: T.textMuted }}>Live API</span>
                        </span>
                    </div>
                </div>
                <p style={{ fontSize: 14, color: T.textMuted, marginBottom: 28, maxWidth: 540 }}>
                    Copy-paste examples against the live API. Toggle response preview to see exactly what comes back.
                </p>
                <div style={{ display: 'flex', gap: 8, marginBottom: 20, flexWrap: 'wrap' }}>
                    {Object.keys(EXAMPLES).map((name, idx) => (
                        <button key={name} onClick={() => setActiveExample(name)} style={{
                            padding: '8px 18px', fontSize: 13, fontWeight: 500, borderRadius: 8,
                            background: activeExample === name ? T.accentBg : 'transparent',
                            color: activeExample === name ? T.accent : T.textMuted,
                            border: `1px solid ${activeExample === name ? T.accentBorder : T.border}`,
                            cursor: 'pointer', transition: 'all 0.15s',
                        }}>
                            {name} <span className="re-nav-shortcuts" style={{ marginLeft: 4, opacity: 0.4, fontSize: 11 }}>{idx + 1}</span>
                        </button>
                    ))}
                </div>
                <CodeBlock examples={EXAMPLES[activeExample]} response={EXAMPLES[activeExample].response} />
            </div>
        </section>
    );
}
