import { beforeEach, describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import ReviewPage from '@/app/review/page';

const mockUseAuth = vi.hoisted(() => vi.fn());
const mockStartTutorial = vi.hoisted(() => vi.fn());

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => mockUseAuth(),
}));

vi.mock('@/components/dashboard/curator-review', () => ({
    CuratorReview: () => <div>Curator Review Content</div>,
}));

vi.mock('@/components/layout/page-container', () => ({
    PageContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
}));

vi.mock('@/components/layout/workflow-stepper', () => ({
    WorkflowStepper: () => <div>Workflow Stepper</div>,
}));

vi.mock('@/components/ui/tutorial', () => ({
    Tutorial: () => null,
    useTutorial: () => ({
        isOpen: false,
        startTutorial: mockStartTutorial,
        closeTutorial: vi.fn(),
    }),
    reviewTutorialSteps: [],
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
}));

vi.mock('lucide-react', () => {
    const Stub = (props: any) => <svg {...props} />;
    return {
        ShieldCheck: Stub,
        ClipboardCheck: Stub,
        Lightbulb: Stub,
        ArrowRight: Stub,
        Upload: Stub,
        HelpCircle: Stub,
    };
});

describe('ReviewPage', () => {
    beforeEach(() => {
        vi.clearAllMocks();
    });

    it('shows an admin-capability warning instead of an API key warning', () => {
        mockUseAuth.mockReturnValue({
            hasAdminSession: false,
            hasTenantSession: false,
            isAuthenticated: false,
            isOnboarded: false,
        });

        render(<ReviewPage />);

        expect(screen.getByText('Review access required')).toBeInTheDocument();
        expect(screen.getByText(/sign in with a workspace admin or sysadmin account/i)).toBeInTheDocument();
        expect(screen.queryByText('API Key Required')).not.toBeInTheDocument();
        expect(screen.getByRole('link', { name: /sign in/i })).toHaveAttribute('href', '/login');
    });

    it('shows the workflow stepper for tenant sessions even when apiKey compatibility fields are unused', () => {
        mockUseAuth.mockReturnValue({
            hasAdminSession: true,
            hasTenantSession: true,
            isAuthenticated: true,
            isOnboarded: true,
        });

        render(<ReviewPage />);

        expect(screen.getByText('Workflow Stepper')).toBeInTheDocument();
        expect(screen.getByText('Curator Review Content')).toBeInTheDocument();
    });
});
