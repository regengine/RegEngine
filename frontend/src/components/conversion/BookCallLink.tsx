'use client';

import Link from 'next/link';
import { forwardRef, type ComponentPropsWithoutRef } from 'react';
import { trackBookCallClick } from '@/lib/conversion-events';

type BookCallLinkProps = ComponentPropsWithoutRef<typeof Link> & {
    placement: string;
    tool?: string;
};

export const BookCallLink = forwardRef<HTMLAnchorElement, BookCallLinkProps>(function BookCallLink(
    { placement, tool, onClick, ...props }, ref
) {
    return (
        <Link
            {...props}
            ref={ref}
            onClick={(event) => {
                trackBookCallClick(placement, tool);
                onClick?.(event);
            }}
        />
    );
});
