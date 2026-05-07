import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import ScanPage from '@/app/dashboard/scan/page';

const mocks = vi.hoisted(() => ({
    useTenant: vi.fn(),
    qrToString: vi.fn(),
}));

vi.mock('@/lib/tenant-context', () => ({
    useTenant: () => mocks.useTenant(),
}));

vi.mock('next/link', () => ({
    default: ({ children, href, ...props }: any) => (
        <a href={href} {...props}>
            {children}
        </a>
    ),
}));

vi.mock('qrcode', () => ({
    toString: (...args: any[]) => mocks.qrToString(...args),
}));

function installDesktopMatchMedia() {
    Object.defineProperty(window, 'matchMedia', {
        configurable: true,
        value: vi.fn().mockImplementation((query: string) => ({
            matches: false,
            media: query,
            onchange: null,
            addListener: vi.fn(),
            removeListener: vi.fn(),
            addEventListener: vi.fn(),
            removeEventListener: vi.fn(),
            dispatchEvent: vi.fn(),
        })),
    });
}

describe('ScanPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        installDesktopMatchMedia();
        mocks.useTenant.mockReturnValue({ tenantId: 'tenant-123' });
        mocks.qrToString.mockResolvedValue('<svg data-testid="mock-qr" />');
    });

    it('scopes shared capture links to the active dashboard tenant', () => {
        render(<ScanPage />);

        expect(screen.getByText('Shared capture links stay scoped to tenant tenant-123.')).toBeInTheDocument();
        expect(screen.getByRole('link', { name: /open scanner in new tab/i })).toHaveAttribute(
            'href',
            '/mobile/capture?tenant_id=tenant-123',
        );
        expect(
            screen.getByText((content) => content.includes('/mobile/capture?tenant_id=tenant-123')),
        ).toBeInTheDocument();
    });
});
