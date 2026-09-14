"use client";

import * as React from "react";
import Link from "next/link";

interface BreadcrumbItem {
    label: string;
    href?: string;
}

interface BreadcrumbsProps {
    items: BreadcrumbItem[];
    className?: string;
}

/**
 * The one breadcrumb component for marketing, tools and docs surfaces.
 *
 * (`React` used to be imported at the *bottom* of this file, below the
 * component that uses `React.Fragment` — it only worked because of hoisting.
 * Fixed.)
 *
 * Kept: `nav[aria-label="Breadcrumb"]`, the leading Home link, and
 * `aria-current="page"` on the last item.
 */
export function Breadcrumbs({ items, className }: BreadcrumbsProps) {
    const linkClass =
        "rounded-sm no-underline transition-colors duration-120 hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset motion-reduce:transition-none";

    return (
        <nav aria-label="Breadcrumb" className={`mb-6 text-small text-re-text-tertiary ${className ?? ""}`}>
            <ol className="flex list-none flex-wrap items-center gap-1.5 p-0">
                <li>
                    <Link href="/" className={linkClass}>
                        Home
                    </Link>
                </li>

                {items.map((item) => (
                    <React.Fragment key={item.label}>
                        <li aria-hidden="true" className="text-re-text-muted">
                            /
                        </li>
                        <li className="min-w-0">
                            {item.href ? (
                                <Link href={item.href} className={linkClass}>
                                    {item.label}
                                </Link>
                            ) : (
                                <span className="font-medium text-re-text-primary" aria-current="page">
                                    {item.label}
                                </span>
                            )}
                        </li>
                    </React.Fragment>
                ))}
            </ol>
        </nav>
    );
}
