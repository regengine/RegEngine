import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import CompliancePage from '@/app/compliance/page';

const mockUseAuth = vi.hoisted(() => vi.fn());
const mockUseIndustries = vi.hoisted(() => vi.fn());
const mockUseChecklists = vi.hoisted(() => vi.fn());

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/hooks/use-api', () => ({
    useIndustries: (...args: any[]) => mockUseIndustries(...args),
    useChecklists: (...args: any[]) => mockUseChecklists(...args),
}));

vi.mock('@/components/layout/page-container', () => ({
    PageContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/ui/card', () => ({
    Card: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardContent: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardHeader: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardTitle: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    CardDescription: ({ children, ...props }: any) => <div {...props}>{children}</div>,
}));

vi.mock('@/components/ui/button', () => ({
    Button: ({ children, ...props }: any) => <button {...props}>{children}</button>,
}));

vi.mock('@/components/ui/badge', () => ({
    Badge: ({ children, ...props }: any) => <span {...props}>{children}</span>,
}));

// Spread the real module: these suites only need to replace <Input> itself, and
// a hand-written factory silently breaks any page importing another export
// (fieldControlClasses, the shared control recipe) the moment one is added.
vi.mock('@/components/ui/input', async (importOriginal) => ({
    ...(await importOriginal<typeof import('@/components/ui/input')>()),
    Input: (props: any) => <input {...props} />,
}));

vi.mock('@/components/ui/skeleton', () => ({
    ChecklistCardSkeleton: () => <div>Checklist Skeleton</div>,
    Skeleton: (props: any) => <div {...props} />,
}));

vi.mock('@/components/ui/tooltip', () => ({
    HelpTooltip: () => null,
}));

vi.mock('next/link', () => ({
    default: ({ children, href }: { children: React.ReactNode; href: string }) => <a href={href}>{children}</a>,
}));

vi.mock('framer-motion', () => ({
    motion: {
        div: ({ children, ...props }: any) => <div {...props}>{children}</div>,
    },
    AnimatePresence: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}));

vi.mock('lucide-react', () => {
    const Stub = (props: any) => <svg {...props} />;
    return {
        CheckCircle: Stub,
        Search: Stub,
        Shield: Stub,
        ArrowRight: Stub,
        Upload: Stub,
        Lightbulb: Stub,
    };
});

describe('CompliancePage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
        mockUseIndustries.mockReturnValue({
            data: [],
            isLoading: false,
        });
        mockUseChecklists.mockReturnValue({
            data: [],
            isLoading: false,
        });
    });

    it('shows a workspace sign-in prompt instead of an API key prompt for signed-out users', () => {
        mockUseAuth.mockReturnValue({
            hasTenantSession: false,
            isAuthenticated: false,
        });

        render(<CompliancePage />);

        expect(screen.getByText('Sign in to connect a workspace')).toBeInTheDocument();
        expect(screen.queryByText(/api key/i)).not.toBeInTheDocument();
        expect(screen.getAllByRole('link', { name: /sign in/i }).every((link) => link.getAttribute('href') === '/login')).toBe(true);
    });

    it('nudges authenticated users to finish setup when they do not have a tenant session yet', () => {
        mockUseAuth.mockReturnValue({
            hasTenantSession: false,
            isAuthenticated: true,
        });

        render(<CompliancePage />);

        expect(screen.getByText('Finish workspace setup')).toBeInTheDocument();
        expect(screen.getAllByRole('link', { name: /finish setup/i }).every((link) => link.getAttribute('href') === '/onboarding')).toBe(true);
    });
});
