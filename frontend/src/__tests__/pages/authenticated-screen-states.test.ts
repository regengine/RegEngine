import fs from 'node:fs';
import path from 'node:path';
import { describe, expect, it } from 'vitest';
import { AUTHENTICATED_APP_ROUTE_PREFIXES, matchesRoutePrefix } from '@/lib/app-routes';

const REQUIRED_STATE_IDS = [
    'empty',
    'loading',
    'error-500',
    'offline',
    'partial-failure',
    'session-expired-401',
    'permission-revoked-403',
    'rate-limited-429',
    'validation-errors',
    'optimistic-rollback',
] as const;

const REQUIRED_STATE_COLUMNS: Record<(typeof REQUIRED_STATE_IDS)[number], string> = {
    empty: 'Empty',
    loading: 'Loading',
    'error-500': 'Error 500',
    offline: 'Offline',
    'partial-failure': 'Partial failure',
    'session-expired-401': '401 expired',
    'permission-revoked-403': '403 revoked',
    'rate-limited-429': '429 limited',
    'validation-errors': 'Validation',
    'optimistic-rollback': 'Optimistic rollback',
};

const AUTHENTICATED_LAYOUT_PREFIXES = ['/developer/portal', '/api-keys'] as const;
const APP_DIR = path.join(process.cwd(), 'src/app');
const DOC_PATH = path.join(process.cwd(), '../docs/engineering/AUTHENTICATED_SCREEN_STATES.md');

function walkPages(dir: string): string[] {
    return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
        const fullPath = path.join(dir, entry.name);
        if (entry.isDirectory()) return walkPages(fullPath);
        return entry.name === 'page.tsx' ? [fullPath] : [];
    });
}

function routeFromPage(pagePath: string): string {
    const route = pagePath
        .slice(APP_DIR.length)
        .replace(/\/page\.tsx$/, '');
    return route || '/';
}

function discoverAuthenticatedRoutes(): string[] {
    const prefixes = [...AUTHENTICATED_APP_ROUTE_PREFIXES, ...AUTHENTICATED_LAYOUT_PREFIXES];
    return walkPages(APP_DIR)
        .map(routeFromPage)
        .filter((route) => matchesRoutePrefix(route, prefixes))
        .sort();
}

function nearestSegmentFile(route: string, filename: 'loading.tsx' | 'error.tsx'): string | null {
    const segments = route.split('/').filter(Boolean);
    for (let index = segments.length; index >= 1; index -= 1) {
        const candidate = path.join(APP_DIR, ...segments.slice(0, index), filename);
        if (fs.existsSync(candidate)) return candidate;
    }
    return null;
}

function splitMarkdownRow(row: string): string[] {
    return row
        .split('|')
        .slice(1, -1)
        .map((cell) => cell.trim());
}

function parseScreenMatrix(markdown: string) {
    const matrixStart = markdown.indexOf('## Screen Matrix');
    const matrixSection = matrixStart >= 0 ? markdown.slice(matrixStart) : '';
    const rows = matrixSection
        .split('\n')
        .filter((line) => line.startsWith('|'));

    const headers = rows[0] ? splitMarkdownRow(rows[0]) : [];
    const bodyRows = rows
        .slice(2)
        .map(splitMarkdownRow)
        .filter((cells) => cells.length === headers.length);
    const routeIndex = headers.indexOf('Route');
    const testIndex = headers.indexOf('Test');
    const stateIndices = Object.fromEntries(
        REQUIRED_STATE_IDS.map((state) => [state, headers.indexOf(REQUIRED_STATE_COLUMNS[state])]),
    ) as Record<(typeof REQUIRED_STATE_IDS)[number], number>;

    return {
        headers,
        routeIndex,
        testIndex,
        stateIndices,
        rows: new Map(
            bodyRows.map((cells) => [
                cells[routeIndex]?.replaceAll('`', ''),
                cells,
            ]),
        ),
    };
}

describe('authenticated screen state coverage', () => {
    it('documents all required states for every authenticated screen', () => {
        const routes = discoverAuthenticatedRoutes();

        expect(fs.existsSync(DOC_PATH), 'authenticated screen-state documentation must exist').toBe(true);
        const markdown = fs.existsSync(DOC_PATH) ? fs.readFileSync(DOC_PATH, 'utf8') : '';

        const matrix = parseScreenMatrix(markdown);
        expect(matrix.headers).toContain('Route');
        expect(matrix.headers).toContain('Test');
        for (const label of Object.values(REQUIRED_STATE_COLUMNS)) {
            expect(matrix.headers).toContain(label);
        }

        const missingRoutes = routes.filter((route) => !matrix.rows.has(route));
        const extraRoutes = Array.from(matrix.rows.keys()).filter((route) => !routes.includes(route));
        expect(missingRoutes).toEqual([]);
        expect(extraRoutes).toEqual([]);

        const missingStates = routes.flatMap((route) => {
            const row = matrix.rows.get(route) ?? [];
            return REQUIRED_STATE_IDS
                .filter((state) => !['C', 'N/A'].includes(row[matrix.stateIndices[state]]))
                .map((state) => `${route} -> ${state}`);
        });
        expect(missingStates).toEqual([]);
    });

    it('keeps loading and error fallbacks wired for every authenticated screen', () => {
        const routes = discoverAuthenticatedRoutes();

        const missingLoading = routes.filter((route) => !nearestSegmentFile(route, 'loading.tsx'));
        const missingError = routes.filter((route) => !nearestSegmentFile(route, 'error.tsx'));

        expect(missingLoading).toEqual([]);
        expect(missingError).toEqual([]);
    });

    it('references existing automated tests from every documented state row', () => {
        expect(fs.existsSync(DOC_PATH), 'authenticated screen-state documentation must exist').toBe(true);
        const markdown = fs.existsSync(DOC_PATH) ? fs.readFileSync(DOC_PATH, 'utf8') : '';
        const routes = discoverAuthenticatedRoutes();
        const matrix = parseScreenMatrix(markdown);

        const missingTestReferences = routes.flatMap((route) => {
            const row = matrix.rows.get(route) ?? [];
            return row[matrix.testIndex]?.startsWith('`') ? [] : [route];
        });
        expect(missingTestReferences).toEqual([]);

        const testPaths = Array.from(markdown.matchAll(/`((?:src|tests)\/[^`]+)`/g)).map((match) => match[1]);
        const missingFiles = testPaths
            .filter((testPath) => testPath.startsWith('src/') || testPath.startsWith('tests/'))
            .filter((testPath) => !fs.existsSync(path.join(process.cwd(), testPath)));

        expect(missingFiles).toEqual([]);
    });
});
