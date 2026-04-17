// ESLint flat config — required by ESLint v9+ and Next.js 16.
// Replaces the legacy .eslintrc.json format. The `next lint` command was
// removed in Next.js 16 (see "next --help" — no `lint` subcommand); this
// file lets `eslint` run directly via the `lint` script in package.json.

import nextCoreWebVitals from 'eslint-config-next/core-web-vitals';

export default [
    ...nextCoreWebVitals,
    {
        // Ignore build artifacts and generated output.
        ignores: [
            '.next/**',
            'node_modules/**',
            'public/**',
            'test-results/**',
            'build_output.txt',
            'build_v2_log.txt',
        ],
    },
    {
        rules: {
            'react/no-unescaped-entities': 'off',
            'react/display-name': 'off',
            'react/jsx-no-comment-textnodes': 'warn',
            'react-hooks/exhaustive-deps': 'warn',
            '@next/next/no-img-element': 'off',
            '@next/next/no-page-custom-font': 'warn',
            'no-console': ['warn', { allow: ['warn', 'error'] }],

            // Newer eslint-plugin-react-hooks v7 rules that weren't enforced
            // under the old `.eslintrc.json` config (lint has been effectively
            // off since the Next.js 16 upgrade silently broke `next lint`).
            // Downgraded to warnings so existing violations don't block CI;
            // tracked for follow-up cleanup.
            'react-hooks/set-state-in-effect': 'warn',
            'react-hooks/purity': 'warn',
            'react-hooks/immutability': 'warn',
            'react-hooks/refs': 'warn',

            // Pre-existing <a> tags in src/app/sandbox/results/[id]/SharedSandboxResult.tsx
            // pointing at /#sandbox. Downgraded to warn to unblock CI; a
            // separate PR should migrate to next/link.
            '@next/next/no-html-link-for-pages': 'warn',
        },
    },
];
