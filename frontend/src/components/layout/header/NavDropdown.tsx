'use client';

import Link from 'next/link';
import { ChevronDown } from 'lucide-react';
import { MARKETING_ALL_TOOLS_LINK, MARKETING_FREE_TOOLS } from '@/components/layout/marketing-nav';
import type { ToolsDropdownProps } from './types';

/**
 * Tools dropdown.
 *
 * Deliberately **not** migrated to `@radix-ui/react-dropdown-menu`: the
 * marketing header owns the open state, the hover-intent timer, the outside
 * -click listener, the roving ArrowUp/ArrowDown handler and the Escape
 * return-focus behaviour, and it reaches into this subtree through
 * `toolsWrapperRef` to find `[role="menuitem"]`. Radix portals its content out
 * of that subtree and overwrites `aria-controls` with a generated id, which
 * would break both the header's keyboard handler and the
 * `aria-controls="tools-dropdown"` contract the tests key off. Restyled in
 * place instead, with every aria hook preserved.
 *
 * Ledger rows, not icon cards (SPEC §6): title + one-line description, the
 * whole row is the link. Icons are never boxed in a tinted square (SPEC §0.7).
 */
export function NavDropdown({
    toolsOpen,
    setToolsOpen,
    toolsWrapperRef,
    toolsButtonRef,
    handleToolsEnter,
    handleToolsLeave,
    handleToolsKeyDown,
    focusFirstToolsItem,
}: ToolsDropdownProps) {
    const AllToolsIcon = MARKETING_ALL_TOOLS_LINK.icon;

    const itemClass =
        'flex items-start gap-3 px-4 py-2.5 no-underline transition-colors duration-120 hover:bg-re-surface-inset focus-visible:outline-none focus-visible:bg-re-surface-inset motion-reduce:transition-none';

    return (
        <div
            ref={toolsWrapperRef}
            className="relative"
            onMouseEnter={handleToolsEnter}
            onMouseLeave={handleToolsLeave}
            onKeyDown={handleToolsKeyDown}
        >
            <button
                ref={toolsButtonRef}
                type="button"
                aria-expanded={toolsOpen}
                aria-haspopup="true"
                aria-controls="tools-dropdown"
                onClick={() => {
                    if (toolsOpen) {
                        setToolsOpen(false);
                    } else {
                        handleToolsEnter();
                    }
                }}
                onKeyDown={(e) => {
                    if (e.key === 'Escape') {
                        setToolsOpen(false);
                        return;
                    }
                    if (e.key === 'ArrowDown') {
                        e.preventDefault();
                        if (!toolsOpen) {
                            setToolsOpen(true);
                        }
                        focusFirstToolsItem();
                    }
                }}
                className={`inline-flex items-center gap-1 whitespace-nowrap rounded-sm bg-transparent text-ui font-medium normal-case ${
                    toolsOpen ? 'text-re-text-primary' : 'text-re-text-secondary'
                } transition-colors duration-120 hover:text-re-text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset motion-reduce:transition-none`}
            >
                Tools
                <ChevronDown
                    aria-hidden="true"
                    size={14}
                    strokeWidth={1.75}
                    className={`transition-transform duration-180 motion-reduce:transition-none${
                        toolsOpen ? ' rotate-180' : ''
                    }`}
                />
            </button>

            <div
                data-tools-dropdown
                className={`absolute right-0 top-full z-[var(--re-z-popover)] pt-2 transition-[opacity,transform,visibility] duration-240 motion-reduce:transition-none ${
                    toolsOpen
                        ? 'visible translate-y-0 opacity-100'
                        : 'invisible translate-y-2 opacity-0 pointer-events-none'
                }`}
            >
                <div
                    id="tools-dropdown"
                    role="menu"
                    aria-label="Free compliance tools"
                    aria-hidden={!toolsOpen}
                    className="min-w-[288px] overflow-hidden rounded-lg border border-[var(--re-nav-dropdown-border)] bg-[var(--re-nav-dropdown-bg)] py-1.5 shadow-re-md"
                >
                    <div className="px-4 pb-1.5 pt-1 text-label uppercase text-re-text-muted">
                        Featured Compliance Tools
                    </div>

                    {MARKETING_FREE_TOOLS.map((tool) => (
                        <Link
                            key={tool.href}
                            href={tool.href}
                            role="menuitem"
                            tabIndex={toolsOpen ? 0 : -1}
                            className={itemClass}
                            onClick={() => setToolsOpen(false)}
                        >
                            <tool.icon
                                aria-hidden="true"
                                size={16}
                                strokeWidth={1.75}
                                className="mt-0.5 shrink-0 text-re-text-tertiary"
                            />
                            <span className="min-w-0">
                                <span className="block text-ui font-medium text-re-text-primary">{tool.label}</span>
                                <span className="mt-0.5 block text-small text-re-text-tertiary">{tool.desc}</span>
                            </span>
                        </Link>
                    ))}

                    <div aria-hidden="true" className="my-1.5 h-px bg-[var(--re-nav-divider)]" />

                    <Link
                        href={MARKETING_ALL_TOOLS_LINK.href}
                        role="menuitem"
                        tabIndex={toolsOpen ? 0 : -1}
                        className={itemClass}
                        onClick={() => setToolsOpen(false)}
                    >
                        <AllToolsIcon
                            aria-hidden="true"
                            size={16}
                            strokeWidth={1.75}
                            className="mt-0.5 shrink-0 text-re-text-tertiary"
                        />
                        <span className="min-w-0">
                            <span className="block text-ui font-medium text-re-text-primary">
                                {MARKETING_ALL_TOOLS_LINK.label}
                            </span>
                            <span className="mt-0.5 block text-small text-re-text-tertiary">
                                {MARKETING_ALL_TOOLS_LINK.desc}
                            </span>
                        </span>
                    </Link>
                </div>
            </div>
        </div>
    );
}
