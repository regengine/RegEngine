import { describe, it, expect, afterEach, vi } from 'vitest';
import {
    experimentalFeaturesEnabled,
    filterExperimentalLinks,
    filterExperimentalToolLinks,
    isExperimentalHref,
    isExperimentalToolHref,
} from '@/lib/experimental-features';

describe('experimental-features', () => {
    afterEach(() => {
        vi.unstubAllEnvs();
    });

    describe('experimentalFeaturesEnabled', () => {
        it('is false when the env var is unset', () => {
            vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', '');
            expect(experimentalFeaturesEnabled()).toBe(false);
        });

        it('is false for arbitrary values', () => {
            vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', 'yes');
            expect(experimentalFeaturesEnabled()).toBe(false);
        });

        it('is true for "1" and "true"', () => {
            vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', '1');
            expect(experimentalFeaturesEnabled()).toBe(true);
            vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', 'true');
            expect(experimentalFeaturesEnabled()).toBe(true);
        });
    });

    describe('isExperimentalToolHref', () => {
        it('matches experimental tool pages', () => {
            expect(isExperimentalToolHref('/tools/ask')).toBe(true);
            expect(isExperimentalToolHref('/tools/knowledge-graph')).toBe(true);
            expect(isExperimentalToolHref('/tools/label-scanner')).toBe(true);
            expect(isExperimentalToolHref('/tools/inflow-lab')).toBe(true);
            expect(isExperimentalToolHref('/tools/ask?q=lot')).toBe(true);
        });

        it('does not match stable tools or non-tool routes', () => {
            expect(isExperimentalToolHref('/tools/ftl-checker')).toBe(false);
            expect(isExperimentalToolHref('/tools/scan')).toBe(false);
            expect(isExperimentalToolHref('/docs/connectors/inflow-lab')).toBe(false);
            expect(isExperimentalToolHref('/dashboard')).toBe(false);
        });
    });

    describe('filterExperimentalToolLinks', () => {
        const links = [
            { href: '/tools/ftl-checker', title: 'FTL' },
            { href: '/tools/label-scanner', title: 'Label Scanner' },
            { href: '/tools/inflow-lab', title: 'Inflow Lab' },
        ];

        it('drops experimental links when the flag is off', () => {
            vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', '');
            expect(filterExperimentalToolLinks(links).map((l) => l.href)).toEqual([
                '/tools/ftl-checker',
            ]);
        });

        it('passes everything through when the flag is on', () => {
            vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', 'true');
            expect(filterExperimentalToolLinks(links)).toEqual(links);
        });
    });

    describe('isExperimentalHref', () => {
        it('matches gated app pages and experimental tools', () => {
            expect(isExperimentalHref('/dashboard/inflow-lab')).toBe(true);
            expect(isExperimentalHref('/dashboard/scan')).toBe(true);
            expect(isExperimentalHref('/ingest/curation')).toBe(true);
            expect(isExperimentalHref('/fsma')).toBe(true);
            expect(isExperimentalHref('/fsma?tab=drills')).toBe(true);
            expect(isExperimentalHref('/fsma/field-capture')).toBe(true);
            expect(isExperimentalHref('/tools/inflow-lab')).toBe(true);
        });

        it('does not match stable pages', () => {
            expect(isExperimentalHref('/dashboard')).toBe(false);
            expect(isExperimentalHref('/dashboard/compliance')).toBe(false);
            expect(isExperimentalHref('/fsma/assessment')).toBe(false);
            expect(isExperimentalHref('/fsma-204')).toBe(false);
            expect(isExperimentalHref('/ingest')).toBe(false);
        });
    });

    describe('filterExperimentalLinks', () => {
        const links = [
            { href: '/dashboard/suppliers', title: 'Suppliers' },
            { href: '/dashboard/inflow-lab', title: 'Inflow Lab' },
            { href: '/ingest/curation', title: 'Curation' },
        ];

        it('drops gated page links when the flag is off', () => {
            vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', '');
            expect(filterExperimentalLinks(links).map((l) => l.href)).toEqual([
                '/dashboard/suppliers',
            ]);
        });

        it('passes everything through when the flag is on', () => {
            vi.stubEnv('NEXT_PUBLIC_ENABLE_EXPERIMENTAL_FEATURES', 'true');
            expect(filterExperimentalLinks(links)).toEqual(links);
        });
    });
});
