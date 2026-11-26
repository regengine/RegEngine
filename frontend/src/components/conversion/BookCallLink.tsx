'use client';

import Link from 'next/link';
import { forwardRef, type ComponentPropsWithoutRef } from 'react';
import { trackBookCallClick } from '@/lib/conversion-events';
import { ph } from '@/lib/posthog-provider';

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
                // Primary contact CTA (AN1): the placement is the stable cta_id.
                ph.ctaClick({ cta_id: placement });
                onClick?.(event);
            }}
        />
    );
});
