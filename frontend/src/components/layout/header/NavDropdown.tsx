'use client';

import Link from 'next/link';
import { ChevronDown } from 'lucide-react';
import { MARKETING_ALL_TOOLS_LINK, MARKETING_FREE_TOOLS } from '@/components/layout/marketing-nav';
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
    const AllToolsIcon = MARKETING_ALL_TOOLS_LINK.icon;

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
                style={{
                    fontSize: "12px",
                    fontWeight: 600,
                    fontFamily: "var(--re-font-mono)",
                    textTransform: "uppercase",
                    color: "var(--re-text-primary)",
                    background: "transparent",
                    padding: "8px 14px",
                    borderRadius: "var(--re-radius-md)",
                    textDecoration: "none",
                    transition: "all var(--re-transition-normal)",
                    cursor: "pointer",
                    display: "inline-flex",
                    alignItems: "center",
                    gap: "6px",
                    border: "1px solid var(--re-surface-border)",
                    whiteSpace: "nowrap",
                }}
            >
                Tools
                <ChevronDown
                    aria-hidden="true"
                    size={14}
                    style={{
                        transition: "transform var(--re-transition-normal)",
                        transform: toolsOpen ? "rotate(180deg)" : "rotate(0)",
                    }}
                />
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
                    borderRadius: "var(--re-radius-md)",
                    opacity: toolsOpen ? 1 : 0,
                    visibility: toolsOpen ? "visible" : "hidden",
                    pointerEvents: toolsOpen ? "auto" : "none",
                    transform: toolsOpen ? "translateY(0)" : "translateY(10px)",
                    transition: "opacity var(--re-transition-slow), transform var(--re-transition-slow), visibility var(--re-transition-slow)",
                    zIndex: "var(--re-z-popover)",
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
                        borderRadius: "var(--re-radius-lg)",
                        padding: "8px 0",
                        minWidth: "280px",
                        backdropFilter: "blur(16px)",
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
                            <span
                                aria-hidden="true"
                                className="flex h-8 w-8 items-center justify-center rounded-sm border border-[var(--re-surface-border)] bg-[var(--re-surface-elevated)] text-[var(--re-text-primary)]"
                            >
                                <tool.icon size={15} strokeWidth={2} />
                            </span>
                            <div>
                                <div className="text-[13px] font-medium text-re-text-primary">{tool.label}</div>
                                <div className="text-[11px] text-re-text-muted">{tool.desc}</div>
                            </div>
                        </Link>
                    ))}
                    <div style={{ height: "1px", background: "var(--re-nav-divider)", margin: "6px 12px" }} />
                    <Link
                        href={MARKETING_ALL_TOOLS_LINK.href}
                        role="menuitem"
                        tabIndex={toolsOpen ? 0 : -1}
                        className="flex items-center gap-2.5 py-2.5 px-4 no-underline transition-[background] duration-150"
                        onClick={() => setToolsOpen(false)}
                        onMouseEnter={(e) => ((e.currentTarget as HTMLElement).style.background = "var(--re-nav-hover)")}
                        onMouseLeave={(e) => ((e.currentTarget as HTMLElement).style.background = "transparent")}
                    >
                        <span
                            aria-hidden="true"
                            className="flex h-8 w-8 items-center justify-center rounded-lg border border-[var(--re-brand)]/20 bg-[var(--re-brand-muted)] text-[var(--re-brand)]"
                        >
                            <AllToolsIcon size={15} strokeWidth={2} />
                        </span>
                        <div>
                            <div className="text-[13px] font-semibold text-re-text-primary">{MARKETING_ALL_TOOLS_LINK.label}</div>
                            <div className="text-[11px] text-re-text-muted">{MARKETING_ALL_TOOLS_LINK.desc}</div>
                        </div>
                    </Link>
                </div>
            </div>
        </div>
    );
}
