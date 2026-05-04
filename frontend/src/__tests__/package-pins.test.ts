import { readFileSync } from 'node:fs';
import { join } from 'node:path';

import { describe, expect, it } from 'vitest';

const EXACT_PINNED_DEPENDENCIES = ['next', '@sentry/nextjs', '@supabase/supabase-js'];
const RANGE_PREFIX = /^[\^~<>=*]| \|\| | - /;

describe('frontend dependency pinning policy', () => {
    it('exact-pins framework-critical runtime dependencies', () => {
        const pkg = JSON.parse(readFileSync(join(process.cwd(), 'package.json'), 'utf-8'));

        for (const dependency of EXACT_PINNED_DEPENDENCIES) {
            const version = pkg.dependencies?.[dependency];
            expect(version, `${dependency} must be declared in dependencies`).toBeTypeOf('string');
            expect(version, `${dependency} must be exact-pinned`).not.toMatch(RANGE_PREFIX);
        }
    });
});
