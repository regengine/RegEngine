import { fireEvent, render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi } from 'vitest';
import { MarketingHeader } from '@/components/layout/marketing-header';

vi.mock('@/lib/auth-context', () => ({
    useAuth: () => ({
        user: null,
        isAuthenticated: false,
        isHydrated: true,
    }),
}));

vi.mock('next-themes', () => ({
    useTheme: () => ({
        theme: 'light',
        setTheme: vi.fn(),
    }),
}));

const getToolsDropdown = () => {
    const dropdown = document.getElementById('tools-dropdown');
    expect(dropdown).toBeInTheDocument();
    return dropdown as HTMLElement;
};

describe('MarketingHeader Tools menu', () => {
    it('keeps the dropdown open when hover commits before button click', async () => {
        const user = userEvent.setup();
        render(<MarketingHeader />);

        const toolsButton = screen.getByRole('button', { name: /^tools$/i });
        expect(getToolsDropdown()).toHaveAttribute('aria-hidden', 'true');

        await user.hover(toolsButton);
        expect(getToolsDropdown()).toHaveAttribute('aria-hidden', 'false');

        await user.click(toolsButton);
        expect(getToolsDropdown()).toHaveAttribute('aria-hidden', 'false');
    });

    it('opens on Tools click and closes on outside click', async () => {
        const user = userEvent.setup();
        render(<MarketingHeader />);

        await user.click(screen.getByRole('button', { name: /^tools$/i }));
        expect(getToolsDropdown()).toHaveAttribute('aria-hidden', 'false');

        fireEvent.mouseDown(document.body);
        expect(getToolsDropdown()).toHaveAttribute('aria-hidden', 'true');
    });

    it('closes when an already click-opened Tools button is clicked again', async () => {
        const user = userEvent.setup();
        render(<MarketingHeader />);

        const toolsButton = screen.getByRole('button', { name: /^tools$/i });
        await user.click(toolsButton);
        expect(getToolsDropdown()).toHaveAttribute('aria-hidden', 'false');

        await user.click(toolsButton);
        expect(getToolsDropdown()).toHaveAttribute('aria-hidden', 'true');
    });
});
