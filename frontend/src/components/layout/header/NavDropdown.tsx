'use client';

import Link from 'next/link';
import { MARKETING_FREE_TOOLS } from '@/components/layout/marketing-nav';
import type { ToolsDropdownProps } from './types';

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
    return (
        <div
            ref={toolsWrapperRef}
            style={{ position: "relative" }}
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
                onClick={() => setToolsOpen((open: boolean) => !open)}
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
                style={{
                    fontSize: "13px",
                    fontWeight: 600,
                    color: "var(--re-surface-base)",
                    background: "var(--re-brand)",
                    padding: "7px 16px",
                    borderRadius: "6px",
                    textDecoration: "none",
                    transition: "all 0.2s",
                    cursor: "pointer",
                    display: "inline-block",
                    border: "none",
                }}
            >
                Free Tools &#9662;
            </button>
            <div
                data-tools-dropdown
                style={{
                    position: "absolute",
                    top: "100%",
                    right: 0,
                    paddingTop: "60px",
                    marginTop: "-30px",
                    background: "none",
                    border: "none",
                    borderRadius: "10px",
                    opacity: toolsOpen ? 1 : 0,
                    pointerEvents: toolsOpen ? "auto" : "none",
                    transform: toolsOpen ? "translateY(0)" : "translateY(10px)",
                    transition: "all 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
                    zIndex: 100,
                }}
            >
                <div
                    id="tools-dropdown"
                    role="menu"
                    aria-label="Free compliance tools"
                    aria-hidden={!toolsOpen}
                    style={{
                        background: "var(--re-nav-dropdown-bg)",
                        border: "1px solid var(--re-nav-dropdown-border)",
                        borderRadius: "12px",
                        padding: "8px 0",
                        minWidth: "280px",
                        backdropFilter: "blur(24px)",
                        boxShadow: "var(--re-nav-dropdown-shadow)",
                    }}
                >
                    <div className="px-4 pt-1 pb-2 text-[10px] font-semibold tracking-wider text-re-text-muted uppercase">
                        Featured Compliance Tools
                    </div>
                    {MARKETING_FREE_TOOLS.map((tool) => (
                        <Link
                            key={tool.href}
                            href={tool.href}
                            role="menuitem"
                            tabIndex={toolsOpen ? 0 : -1}
                            className="flex items-center gap-2.5 py-2 px-4 no-underline transition-[background] duration-150"
                            onClick={() => setToolsOpen(false)}
                            onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "var(--re-nav-hover)")}
                            onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "transparent")}
                        >
                            <span aria-hidden="true" className="text-sm">{tool.emoji}</span>
                            <div>
                                <div className="text-[13px] font-medium text-re-text-primary">{tool.label}</div>
                                <div className="text-[11px] text-re-text-muted">{tool.desc}</div>
                            </div>
                        </Link>
                    ))}
                    <div style={{ height: "1px", background: "var(--re-nav-divider)", margin: "6px 12px" }} />
                    <Link
                        href="/tools"
                        role="menuitem"
                        tabIndex={toolsOpen ? 0 : -1}
                        className="flex items-center gap-2.5 py-2.5 px-4 no-underline transition-[background] duration-150"
                        onClick={() => setToolsOpen(false)}
                        onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "var(--re-nav-hover)")}
                        onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "transparent")}
                    >
                        <span aria-hidden="true" className="text-sm">&#129520;</span>
                        <div>
                            <div className="text-[13px] font-semibold text-re-brand">View All Tools &rarr;</div>
                            <div className="text-[11px] text-re-text-muted">Explore the compliance toolkit</div>
                        </div>
                    </Link>
                </div>
            </div>
        </div>
    );
}
