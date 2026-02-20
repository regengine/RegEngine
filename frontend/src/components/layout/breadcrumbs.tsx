"use client";

import Link from "next/link";
import { ChevronRight } from "lucide-react";

interface BreadcrumbItem {
    label: string;
    href?: string;
}

interface BreadcrumbsProps {
    items: BreadcrumbItem[];
}

export function Breadcrumbs({ items }: BreadcrumbsProps) {
    return (
        <nav aria-label="Breadcrumb" className="text-sm text-muted-foreground mb-6">
            <ol className="flex items-center gap-1.5 list-none p-0 flex-wrap">
                <li>
                    <Link
                        href="/"
                        className="hover:text-[var(--re-brand)] transition-colors"
                    >
                        Home
                    </Link>
                </li>

                {items.map((item, index) => (
                    <React.Fragment key={item.label}>
                        <li aria-hidden="true" className="text-muted-foreground/40">
                            /
                        </li>
                        <li>
                            {item.href ? (
                                <Link
                                    href={item.href}
                                    className="hover:text-[var(--re-brand)] transition-colors"
                                >
                                    {item.label}
                                </Link>
                            ) : (
                                <span className="font-medium text-foreground" aria-current="page">
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

import React from "react"; // For React.Fragment
