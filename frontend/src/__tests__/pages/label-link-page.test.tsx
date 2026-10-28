import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// The global setup mock of next/navigation has no notFound; the page needs one
// that halts rendering the way Next's does.
const notFoundMock = vi.hoisted(() =>
    vi.fn(() => {
        throw new Error('NEXT_NOT_FOUND');
    }),
);
vi.mock('next/navigation', () => ({ notFound: notFoundMock }));

import LabelLinkPage, { generateMetadata } from '@/app/01/[gtin]/10/[lot]/21/[serial]/page';

// Next hands page.tsx the segments re-encoded and generateMetadata the
// decoded ones (see label-link.ts), so each test uses the form its caller
// really receives.
const RAW = { gtin: '00012345678905', lot: 'LOT-2024%2F001', serial: '000123456789012345' };
const DECODED = { ...RAW, lot: 'LOT-2024/001' };

describe('label QR landing page (/01/{gtin}/10/{lot}/21/{serial})', () => {
    beforeEach(() => {
        notFoundMock.mockClear();
    });

    it('shows what the code encodes and links to /trace with the lot prefilled', async () => {
        render(await LabelLinkPage({ params: Promise.resolve(RAW) }));

        expect(screen.getByRole('heading', { name: 'Lot LOT-2024/001' })).toBeInTheDocument();
        expect(screen.getByText('00012345678905')).toBeInTheDocument();
        expect(screen.getByText('000123456789012345')).toBeInTheDocument();
        expect(screen.getByText('Valid')).toBeInTheDocument();
        expect(screen.getByRole('link', { name: 'Trace this lot' })).toHaveAttribute(
            'href',
            '/trace?tlc=LOT-2024%2F001',
        );
        expect(notFoundMock).not.toHaveBeenCalled();
    });

    it.each([
        ['a GTIN that is not 14 digits', { ...RAW, gtin: 'not-a-gtin' }],
        ['an empty lot', { ...RAW, lot: '' }],
        ['an empty serial', { ...RAW, serial: '' }],
    ])('returns 404 for %s', async (_label, params) => {
        await expect(LabelLinkPage({ params: Promise.resolve(params) })).rejects.toThrow('NEXT_NOT_FOUND');
        expect(notFoundMock).toHaveBeenCalledTimes(1);
    });

    it('is never indexed', async () => {
        const meta = await generateMetadata({ params: Promise.resolve(DECODED) });
        expect(meta.robots).toEqual({ index: false, follow: false });
        expect(meta.title).toBe('Lot LOT-2024/001 | RegEngine label');
    });

    it('does not decode the already-decoded lot a second time in the title', async () => {
        // Lot "A%2FB" reaches generateMetadata as exactly that.
        const meta = await generateMetadata({ params: Promise.resolve({ ...DECODED, lot: 'A%2FB' }) });
        expect(meta.title).toBe('Lot A%2FB | RegEngine label');
    });
});
