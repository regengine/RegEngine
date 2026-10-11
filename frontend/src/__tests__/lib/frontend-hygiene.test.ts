import { readdirSync, readFileSync, existsSync, statSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const ROOT = process.cwd();
const SRC = join(ROOT, 'src');

function sourceFiles(): string[] {
    const out: string[] = [];
    const walk = (dir: string) => {
        for (const entry of readdirSync(dir)) {
            const full = join(dir, entry);
            if (statSync(full).isDirectory()) {
                walk(full);
            } else if (/\.tsx?$/.test(entry) && !/(__tests__|\.test\.|\.spec\.)/.test(full)) {
                out.push(full);
            }
        }
    };
    walk(SRC);
    return out;
}

function enclosingTag(text: string, at: number): string {
    const start = text.lastIndexOf('<', at);
    const end = text.indexOf('>', at);
    return text.slice(start, end + 1);
}

describe('frontend hygiene gates', () => {
    it('has no unregistered service worker file', () => {
        // public/sw.js used to ship without any registration call, so its
        // offline queue and cache rules never ran. Either register a worker
        // deliberately or do not ship one.
        expect(existsSync(join(ROOT, 'public', 'sw.js'))).toBe(false);
    });

    it('knowledge graph has no direct-to-NLP search path', () => {
        // The builder used to POST the (placeholder) API key straight at the
        // NLP service URL from the browser. That URL is unreachable from
        // browsers and duplicates the live /api/nlp/ask proxy used by Ask.
        const file = join(SRC, 'app', 'tools', 'knowledge-graph', 'components', 'KnowledgeGraph.tsx');
        const text = readFileSync(file, 'utf-8');
        expect(text).not.toContain('/api/v1/query/traceability');
        expect(text).not.toContain('runTraceabilityQuery');
        expect(text).not.toContain('X-RegEngine-API-Key');
    });

    it('every target=_blank link carries rel=noopener', () => {
        const bad: string[] = [];
        for (const file of sourceFiles()) {
            const text = readFileSync(file, 'utf-8');
            let at = text.indexOf('target="_blank"');
            while (at !== -1) {
                const tag = enclosingTag(text, at);
                if (!/^<(a|Link)\b/.test(tag) || !/rel=/.test(tag) || !/noopener/.test(tag)) {
                    const line = text.slice(0, at).split('\n').length;
                    bad.push(`${file}:${line}: ${tag.slice(0, 120)}`);
                }
                at = text.indexOf('target="_blank"', at + 1);
            }
        }
        expect(bad).toEqual([]);
    });

    it('every window.open to _blank passes noopener', () => {
        const bad: string[] = [];
        for (const file of sourceFiles()) {
            const text = readFileSync(file, 'utf-8');
            let at = text.indexOf('window.open(');
            while (at !== -1) {
                const stmt = text.slice(at, at + 200);
                if ((stmt.includes("'_blank'") || stmt.includes('"_blank"')) && !stmt.includes('noopener')) {
                    const line = text.slice(0, at).split('\n').length;
                    bad.push(`${file}:${line}`);
                }
                at = text.indexOf('window.open(', at + 1);
            }
        }
        expect(bad).toEqual([]);
    });

    it('client path ids are encodeURIComponent-wrapped', () => {
        const idNames = new Set([
            'tenantId', 'alertId', 'supplierId', 'stepId', 'drillId',
            'caseId', 'requestCaseId', 'eventId', 'runId', 'itemId',
            'userId', 'inviteId', 'facilityId', 'sessionId', 'portalId',
            'profileId', 'requestId', 'keyId', 'jobId', 'checklistId',
            'documentId',
        ]);
        const files = [
            'src/lib/api-hooks.ts',
            'src/lib/api-client.ts',
            'src/hooks/use-control-plane.ts',
            'src/hooks/use-fsma.ts',
            'src/hooks/use-remediation.ts',
            'src/hooks/use-review.ts',
            'src/hooks/use-billing.ts',
            'src/hooks/use-sla.ts',
        ];
        const bad: string[] = [];
        for (const rel of files) {
            const lines = readFileSync(join(ROOT, rel), 'utf-8').split('\n');
            lines.forEach((line, index) => {
                for (const match of line.matchAll(/\$\{([^}]+)\}/g)) {
                    const inner = match[1];
                    if (inner.startsWith('encodeURIComponent(')) continue;
                    if (/^[A-Za-z_$][\w$]*$/.test(inner) && idNames.has(inner)) {
                        const before = line.slice(0, match.index);
                        if (before.endsWith('/')) {
                            bad.push(`${rel}:${index + 1}: ${line.trim().slice(0, 100)}`);
                        }
                    }
                }
            });
        }
        expect(bad).toEqual([]);
    });
});
