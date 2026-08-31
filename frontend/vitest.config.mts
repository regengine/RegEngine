import { defineConfig } from 'vitest/config';
import react from '@vitejs/plugin-react';
import path from 'path';

export default defineConfig({
    plugins: [react()],
    test: {
        environment: 'jsdom',
        globals: true,
        setupFiles: ['./src/__tests__/setup.ts'],
        include: ['src/**/*.{test,spec}.{ts,tsx}'],
        coverage: {
            provider: 'v8',
            reporter: ['text', 'json', 'html', 'lcov'],
            exclude: [
                'node_modules/',
                'src/__tests__/',
                'src/test/',
                '**/*.d.ts',
                '**/*.config.*',
                '**/types/**',
                '.next/**',
                'out/**',
            ],
            // Issue #2845: these were 20 while real coverage sat in the
            // 59-69% range, so the gate had ~40 points of slack and could not
            // have caught any realistic regression. `npm run test:coverage`
            // now runs in CI (frontend-ci.yml), so the numbers finally matter.
            //
            // Each floor is set ~6 points below the value measured on
            // 2026-08-27 — enough headroom that ordinary churn does not trip
            // the build, tight enough that a meaningful drop does:
            //
            //   statements 66.56%  branches 59.68%
            //   functions  59.40%  lines    68.75%
            //
            // Raise these as coverage improves. Lowering one to make a build
            // pass reinstates exactly the false assurance this replaced.
            thresholds: {
                statements: 60,
                branches: 53,
                functions: 53,
                lines: 62,
            },
        },
        testTimeout: 10000,
    },
    resolve: {
        alias: {
            '@': path.resolve(__dirname, './src'),
        },
    },
});
