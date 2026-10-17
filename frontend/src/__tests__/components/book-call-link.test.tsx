import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';
import { BookCallLink } from '@/components/conversion/BookCallLink';
import { Button } from '@/components/ui/button';
import { trackBookCallClick } from '@/lib/conversion-events';

vi.mock('@/lib/conversion-events', () => ({
    trackBookCallClick: vi.fn(),
}));

describe('BookCallLink', () => {
    it('tracks a booking click and keeps the link destination', () => {
        render(
            <Button asChild>
                <BookCallLink href="/contact" placement="home_page" onClick={(event) => event.preventDefault()}>
                    Book a call
                </BookCallLink>
            </Button>,
        );

        const link = screen.getByRole('link', { name: 'Book a call' });
        expect(link).toHaveAttribute('href', '/contact');
        fireEvent.click(link);
        expect(trackBookCallClick).toHaveBeenCalledTimes(1);
        expect(trackBookCallClick).toHaveBeenCalledWith('home_page', undefined);
    });
});
