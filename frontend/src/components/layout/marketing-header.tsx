'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { RegEngineWordmark } from '@/components/layout/regengine-wordmark';
import { DesktopNav, MobileMenu, MobileHamburger } from '@/components/layout/header';

export function MarketingHeader() {
    const pathname = usePathname();
    const [mobileOpen, setMobileOpen] = useState(false);
    const [toolsOpen, setToolsOpen] = useState(false);
    const closeTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
    const toolsWrapperRef = useRef<HTMLDivElement | null>(null);
    const toolsButtonRef = useRef<HTMLButtonElement | null>(null);
    const { user, isAuthenticated, isHydrated } = useAuth();
    // Only show logged-in state when auth is fully verified
    const showLoggedIn = isHydrated && isAuthenticated && !!user;
    const hideHeader =
        pathname === '/mobile/capture' ||
        pathname === '/fsma/field-capture' ||
        pathname.startsWith('/dashboard') ||
        pathname.startsWith('/onboarding');

    // Close mobile menu on route change
    useEffect(() => {
        setMobileOpen(false);
    }, [pathname]);

    // Prevent body scroll when mobile menu is open
    useEffect(() => {
        if (mobileOpen) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = '';
        }
        return () => { document.body.style.overflow = ''; };
    }, [mobileOpen]);

    const handleToolsEnter = () => {
        if (closeTimeoutRef.current) {
            clearTimeout(closeTimeoutRef.current);
            closeTimeoutRef.current = null;
        }
        setToolsOpen(true);
    };

    const handleToolsLeave = () => {
        if (closeTimeoutRef.current) {
            clearTimeout(closeTimeoutRef.current);
        }
        closeTimeoutRef.current = setTimeout(() => {
            setToolsOpen(false);
        }, 500);
    };

    const focusFirstToolsItem = () => {
        requestAnimationFrame(() => {
            const firstItem = toolsWrapperRef.current?.querySelector<HTMLElement>('[role="menuitem"]');
            firstItem?.focus();
        });
    };

    const handleToolsKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
        if (e.key === 'Escape') {
            setToolsOpen(false);
            toolsButtonRef.current?.focus();
            return;
        }

        if (!toolsOpen || (e.key !== 'ArrowDown' && e.key !== 'ArrowUp')) {
            return;
        }

        const menuItems = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('[role="menuitem"]'));
        if (menuItems.length === 0) {
            return;
        }

        e.preventDefault();
        const activeIndex = menuItems.findIndex((item) => item === document.activeElement);

        if (activeIndex === -1) {
            const fallbackIndex = e.key === 'ArrowDown' ? 0 : menuItems.length - 1;
            menuItems[fallbackIndex]?.focus();
            return;
        }

        const nextIndex =
            e.key === 'ArrowDown'
                ? (activeIndex + 1) % menuItems.length
                : (activeIndex - 1 + menuItems.length) % menuItems.length;
        menuItems[nextIndex]?.focus();
    };

    useEffect(() => {
        if (hideHeader) {
            return;
        }

        const handleOutsideInteraction = (event: MouseEvent | TouchEvent) => {
            const target = event.target as Node;
            if (!toolsWrapperRef.current?.contains(target)) {
                setToolsOpen(false);
            }
        };

        document.addEventListener('mousedown', handleOutsideInteraction);
        document.addEventListener('touchstart', handleOutsideInteraction);

        return () => {
            document.removeEventListener('mousedown', handleOutsideInteraction);
            document.removeEventListener('touchstart', handleOutsideInteraction);
            if (closeTimeoutRef.current) {
                clearTimeout(closeTimeoutRef.current);
            }
        };
    }, [hideHeader]);

    if (hideHeader) {
        return null;
    }

    return (
        <>
            <nav
                aria-label="Main navigation"
                style={{
                    position: "sticky",
                    top: 0,
                    zIndex: 50,
                    borderBottom: "1px solid var(--re-nav-border)",
                    backdropFilter: "blur(16px)",
                    WebkitBackdropFilter: "blur(16px)",
                    background: "var(--re-nav-bg)",
                }}
            >
                <div
                    style={{
                        maxWidth: "1120px",
                        margin: "0 auto",
                        padding: "0 clamp(16px, 4vw, 24px)",
                        height: "56px",
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                    }}
                >
                    <Link href="/" style={{ display: "flex", alignItems: "center", gap: "10px", textDecoration: "none", marginRight: "24px", flexShrink: 0 }}>
                        <RegEngineWordmark size="md" />
                    </Link>

                    <DesktopNav
                        user={user}
                        showLoggedIn={showLoggedIn}
                        pathname={pathname}
                        toolsOpen={toolsOpen}
                        setToolsOpen={setToolsOpen}
                        toolsWrapperRef={toolsWrapperRef}
                        toolsButtonRef={toolsButtonRef}
                        handleToolsEnter={handleToolsEnter}
                        handleToolsLeave={handleToolsLeave}
                        handleToolsKeyDown={handleToolsKeyDown}
                        focusFirstToolsItem={focusFirstToolsItem}
                    />

                    <MobileHamburger mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} />
                </div>
            </nav>

            <MobileMenu
                user={user}
                showLoggedIn={showLoggedIn}
                pathname={pathname}
                mobileOpen={mobileOpen}
                setMobileOpen={setMobileOpen}
            />

            {/* Responsive CSS */}
            <style jsx>{`
                @media (max-width: 768px) {
                    .marketing-desktop-nav {
                        display: none !important;
                    }
                    .marketing-mobile-toggle {
                        display: flex !important;
                    }
                }
            `}</style>
        </>
    );
}
