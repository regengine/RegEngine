import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { render } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import VerifyPage from '@/app/verify/page';
import WalkthroughPage from '@/app/walkthrough/page';
import ProofPage from '@/app/proof/page';

vi.mock('framer-motion', () => ({
    motion: {
        div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    },
}));

// The bundle verifier only recomputes hashes against the manifest packaged
// inside the uploaded ZIP. No signature or independently published digest is
// checked, so public copy must not describe a passing result as signed,
// authentic, or proof of RegEngine origin.
const UNBACKED_AUTHENTICITY_CLAIMS = [
    /signed manifest/i,
    /digitally signed/i,
    /cryptographically (signed|verified|proven|secured)/i,
    /tamper-proof/i,
    /hasn't changed since assembly/i,
    /what regengine signed/i,
];

function renderedText(ui: React.ReactElement): string {
    const { container } = render(ui);
    return container.textContent ?? '';
}

describe('public proof-bundle trust copy', () => {
    it('/verify describes results as self-consistency and disclaims publisher authentication', () => {
        const text = renderedText(<VerifyPage />);

        expect(text).toMatch(/does not authenticate who published the bundle/i);
        expect(text).toMatch(/treated as\s+untrusted input/i);
        expect(text).toMatch(/does not verify a signature/i);
        expect(text).toMatch(/does not establish that RegEngine produced the bundle|establish that RegEngine produced the bundle/i);
        expect(text).toMatch(/not.*proof of publisher identity or provenance/i);

        for (const claim of UNBACKED_AUTHENTICITY_CLAIMS) {
            expect(text).not.toMatch(claim);
        }
    });

    it('/walkthrough does not describe the export manifest as signed or origin-proving', () => {
        const text = renderedText(<WalkthroughPage />);

        expect(text).toMatch(/the manifest is not signed/i);
        expect(text).toMatch(/does not by itself establish who produced the package/i);

        for (const claim of UNBACKED_AUTHENTICITY_CLAIMS) {
            expect(text).not.toMatch(claim);
        }
    });

    it('/proof is hidden until it can publish artifacts from a real export', () => {
        expect(() => ProofPage()).toThrow();
    });

    it('verify_chain.py documents that the uploaded manifest is an untrusted commitment', () => {
        const source = readFileSync(
            resolve(process.cwd(), 'public/sdk/verify_chain.py'),
            'utf8',
        );

        expect(source).toMatch(/do not authenticate the\s+issuer/i);
        expect(source).toMatch(/No digital signature or\s+independently trusted hash is verified/i);
    });
});
