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
            thresholds: {
                statements: 20,
                branches: 20,
                functions: 20,
                lines: 20,
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
