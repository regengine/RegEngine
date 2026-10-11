import fs from 'fs';
import path from 'path';
import { describe, expect, it } from 'vitest';
import sitemap, { stableLastModified } from '@/app/sitemap';
import { metadata as homeMetadata } from '@/app/page';
import { metadata as toolsMetadata } from '@/app/tools/page';
import { metadata as ftlMetadata } from '@/app/tools/ftl-checker/page';
import { metadata as cteMetadata } from '@/app/tools/cte-mapper/page';
import { metadata as kdeMetadata } from '@/app/tools/kde-checker/page';
import { metadata as tlcMetadata } from '@/app/tools/tlc-validator/page';
import { metadata as selfMetadata } from '@/app/tools/self-reported-checklist/page';
import { metadata as recordsMetadata } from '@/app/tools/records-request-checklist/page';
import type { Metadata } from 'next';

/**
 * Public snippet limits from the Oct 8, 2026 regengine.co audit.
 * Titles stay at or under 60 characters. Meta descriptions stay at or under 155.
 * Tool names are the same string on the tools index, the page title, and the H1.
 * JSON-LD does not publish offers or prices.
 */

const FRONTEND = process.cwd();
const SRC = path.join(FRONTEND, 'src');
const TITLE_LIMIT = 60;
const DESCRIPTION_LIMIT = 155;
const DASH = /[, -]/;

const HOME_TITLE = 'FSMA 204 Recordkeeping Software | RegEngine';
const HOME_DESCRIPTION =
    'Pre-revenue FSMA 204 recordkeeping software. Free FTL, CTE, KDE, and TLC checkers. The FDA compliance date is July 20, 2028. Not legal advice.';
const HOME_H1 = 'FSMA 204 recordkeeping for the Food Traceability Rule.';

const TOOLS_TITLE = 'Free FSMA 204 Tools | RegEngine';
const TOOLS_DESCRIPTION =
    'Free FTL List Checker, CTE Mapper, KDE checklist, and TLC format check. Self reported lists do not score readiness. FDA date: July 20, 2028.';
const TOOLS_H1 = 'Free tools for FSMA 204 list checks and field checks.';

const TOOLS: { slug: string; name: string; title: string; description: string }[] = [
    {
        slug: 'ftl-checker',
        name: 'FTL List Checker',
        title: 'FTL List Checker for FSMA 204 | RegEngine',
        description:
            'Check foods against the FDA Food Traceability List. This free page does not decide who must keep records. Verify every grouping on the current FDA list.',
    },
    {
        slug: 'cte-mapper',
        name: 'CTE Mapper',
        title: 'FSMA 204 CTE Mapper by Role | RegEngine',
        description:
            'See which Critical Tracking Events usually apply to a role under 21 CFR Part 1 Subpart S. Educational only. Exemptions can change what applies.',
    },
    {
        slug: 'kde-checker',
        name: 'KDE Field Checklist',
        title: 'FSMA 204 KDE Field Checklist | RegEngine',
        description:
            'A starting checklist of Key Data Elements for an FTL food and a Critical Tracking Event. Educational only. Check the rule before you rely on it.',
    },
    {
        slug: 'tlc-validator',
        name: 'TLC Format Check',
        title: 'TLC Format Check for FSMA 204 | RegEngine',
        description:
            'Check a traceability lot code for format and uniqueness assumptions. FDA does not set one TLC format. This free check is not a compliance determination.',
    },
    {
        slug: 'self-reported-checklist',
        name: 'Self Reported Checklist',
        title: 'Self Reported Checklist | FSMA 204 | RegEngine',
        description:
            'You answer and the page echoes what you reported. It does not verify records, score readiness, or decide if you can meet the records request rule.',
    },
    {
        slug: 'records-request-checklist',
        name: 'Records Request Checklist',
        title: 'FSMA 204 Records Request Checklist | RegEngine',
        description:
            'A self reported checklist for an FDA records request under 21 CFR 1.1455. Not a 24 hour test, not a readiness score, and not legal advice.',
    },
];

const PAGE_METADATA: Record<string, Metadata> = {
    'ftl-checker': ftlMetadata,
    'cte-mapper': cteMetadata,
    'kde-checker': kdeMetadata,
    'tlc-validator': tlcMetadata,
    'self-reported-checklist': selfMetadata,
    'records-request-checklist': recordsMetadata,
};

function asText(value: Metadata['title'] | Metadata['description'] | undefined, label: string): string {
    if (typeof value !== 'string') {
        throw new Error(`${label} must be a plain string`);
    }
    return value;
}

function read(rel: string): string {
    return fs.readFileSync(path.join(FRONTEND, rel), 'utf8');
}

function walk(dir: string, out: string[] = []): string[] {
    for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        if (entry.name === '__tests__' || entry.name === 'node_modules') continue;
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(full, out);
        else if (/\.(tsx|ts)$/.test(entry.name)) out.push(full);
    }
    return out;
}

describe('public snippet lengths', () => {
    it('keeps the homepage title, description, and H1 inside the audit copy', () => {
        const title = asText(homeMetadata.title, 'home title');
        const description = asText(homeMetadata.description, 'home description');
        const og = homeMetadata.openGraph;
        const ogTitle = asText(og && 'title' in og ? og.title : undefined, 'home og title');
        const ogDescription = asText(og && 'description' in og ? og.description : undefined, 'home og description');

        expect(title).toBe(HOME_TITLE);
        expect(description).toBe(HOME_DESCRIPTION);
        expect(title.length).toBeLessThanOrEqual(TITLE_LIMIT);
        expect(description.length).toBeLessThanOrEqual(DESCRIPTION_LIMIT);
        expect(ogTitle.length).toBeLessThanOrEqual(TITLE_LIMIT);
        expect(ogDescription.length).toBeLessThanOrEqual(DESCRIPTION_LIMIT);
        expect(`${title} ${description} ${ogTitle} ${ogDescription}`).not.toMatch(DASH);
        expect(read('src/app/page.tsx')).toContain(HOME_H1);
    });

    it('keeps the tools index title, description, and H1 inside the audit copy', () => {
        const title = asText(toolsMetadata.title, 'tools title');
        const description = asText(toolsMetadata.description, 'tools description');
        expect(title).toBe(TOOLS_TITLE);
        expect(description).toBe(TOOLS_DESCRIPTION);
        expect(title.length).toBeLessThanOrEqual(TITLE_LIMIT);
        expect(description.length).toBeLessThanOrEqual(DESCRIPTION_LIMIT);
        expect(`${title} ${description}`).not.toMatch(DASH);
        expect(read('src/app/tools/components/ToolsLandingClient.tsx')).toContain(TOOLS_H1);
    });

    it('keeps each audited tool title and description inside the limits', () => {
        for (const tool of TOOLS) {
            const metadata = PAGE_METADATA[tool.slug];
            const title = asText(metadata.title, tool.slug);
            const description = asText(metadata.description, tool.slug);
            const og = metadata.openGraph;
            const ogDescription = asText(og && 'description' in og ? og.description : undefined, `${tool.slug} og`);
            expect(title, tool.slug).toBe(tool.title);
            expect(description, tool.slug).toBe(tool.description);
            expect(title.length, tool.slug).toBeLessThanOrEqual(TITLE_LIMIT);
            expect(description.length, tool.slug).toBeLessThanOrEqual(DESCRIPTION_LIMIT);
            expect(ogDescription.length, tool.slug).toBeLessThanOrEqual(DESCRIPTION_LIMIT);
            expect(`${title} ${description} ${ogDescription}`, tool.slug).not.toMatch(DASH);
            expect(title, tool.slug).toContain(tool.name);
        }
    });
});

describe('tool names match the index, the title, and the H1', () => {
    const landing = read('src/app/tools/components/ToolsLandingClient.tsx');
    const indexJsonLd = read('src/app/tools/page.tsx');

    it('uses one name on the tools index cards', () => {
        for (const tool of TOOLS) {
            expect(landing, tool.slug).toContain(`'${tool.name}'`);
            expect(indexJsonLd, tool.slug).toContain(`"name": "${tool.name}"`);
        }
    });

    it('uses that same name as the only H1 on each tool page', () => {
        const h1Sources: Record<string, string> = {
            'ftl-checker': read('src/app/tools/ftl-checker/components/FTLCheckerClient.tsx'),
            'cte-mapper': read('src/app/tools/cte-mapper/components/CTEMapperClient.tsx'),
            'kde-checker': read('src/app/tools/kde-checker/components/KDECheckerClient.tsx'),
            'tlc-validator': read('src/app/tools/tlc-validator/components/TLCValidatorClient.tsx'),
            'self-reported-checklist': read('src/app/tools/self-reported-checklist/components/SelfReportedChecklistClient.tsx'),
            'records-request-checklist': read('src/app/tools/records-request-checklist/components/RecordsRequestChecklistClient.tsx'),
        };
        for (const tool of TOOLS) {
            const source = h1Sources[tool.slug];
            expect(source, tool.slug).toContain(tool.name);
            expect(source, tool.slug).not.toContain('CTE Coverage Mapper');
            expect(source, tool.slug).not.toContain('KDE Checklist Builder');
            expect(source, tool.slug).not.toContain('TLC Validator');
        }
        expect(read('src/app/tools/cte-mapper/page.tsx')).not.toMatch(/<h1[\s>]/);
        expect(read('src/app/tools/self-reported-checklist/page.tsx')).not.toMatch(/<h1[\s>]/);
        expect(read('src/app/tools/self-reported-checklist/components/SelfReportedChecklistClient.tsx')).toContain(
            'heading="Self Reported Checklist"',
        );
    });
});

describe('TLC snippet does not claim an FDA format', () => {
    it('says FDA does not set one TLC format', () => {
        const description = asText(tlcMetadata.description, 'tlc description');
        const og = tlcMetadata.openGraph;
        const ogDescription = asText(og && 'description' in og ? og.description : undefined, 'tlc og');
        const page = read('src/app/tools/tlc-validator/page.tsx');
        const client = read('src/app/tools/tlc-validator/components/TLCValidatorClient.tsx');
        for (const text of [description, ogDescription, page, client]) {
            expect(text).not.toMatch(/FDA uniqueness/);
            expect(text).not.toMatch(/GS1 standards and FDA/);
            expect(text).not.toMatch(/against GS1 and FDA/);
            expect(text).not.toMatch(/FDA FSMA 204 requirements/);
        }
        expect(description).toContain('FDA does not set one TLC format');
        expect(ogDescription).toContain('FDA does not set one TLC format');
    });
});

describe('JSON-LD has no offers or prices', () => {
    it('does not publish Offer, AggregateOffer, or price fields', () => {
        const hits: string[] = [];
        for (const file of walk(SRC)) {
            const text = fs.readFileSync(file, 'utf8');
            if (!text.includes('@type') && !text.includes('AggregateOffer')) continue;
            if (
                text.includes('AggregateOffer')
                || text.includes('priceCurrency')
                || text.includes('lowPrice')
                || text.includes('highPrice')
                || text.includes("'@type': 'Offer'")
                || text.includes('"@type": "Offer"')
                || text.includes('"@type": "AggregateOffer"')
            ) {
                hits.push(path.relative(FRONTEND, file));
            }
        }
        expect(hits).toEqual([]);
    });
});

describe('sitemap lastmod and readiness redirect', () => {
    const entries = sitemap();

    it('does not list the readiness-assessment redirect', () => {
        const urls = entries.map((entry) => entry.url);
        expect(urls).not.toContain('https://regengine.co/tools/readiness-assessment');
    });

    it('does not list next.config redirect sources', () => {
        const config = read('next.config.js');
        const sources = [...config.matchAll(/source:\s*'([^']+)'/g)].map((match) => match[1]);
        const listed = entries
            .map((entry) => entry.url.replace('https://regengine.co', '') || '/')
            .filter((urlPath) => sources.includes(urlPath));
        expect(listed).toEqual([]);
    });

    it('keeps lastmod values stable and valid across calls', () => {
        const again = sitemap();
        expect(again.map((entry) => entry.lastModified ?? null)).toEqual(
            entries.map((entry) => entry.lastModified ?? null),
        );
        for (const entry of entries) {
            if (entry.lastModified == null) continue;
            const value = entry.lastModified instanceof Date
                ? entry.lastModified.toISOString()
                : String(entry.lastModified);
            expect(value, entry.url).toMatch(/^\d{4}-\d{2}-\d{2}(T\d{2}:\d{2}:\d{2}(?:\.\d{3})?Z)?$/);
            expect(Number.isNaN(Date.parse(value)), entry.url).toBe(false);
        }
    });

    it('drops a lastmod that would throw when Next serializes it', () => {
        expect(stableLastModified(undefined)).toBeUndefined();
        expect(stableLastModified('not-a-date')).toBeUndefined();
        expect(stableLastModified('2026-02-31')).toBeUndefined();
        expect(stableLastModified('2026-04-01')).toBe('2026-04-01');
    });
});
