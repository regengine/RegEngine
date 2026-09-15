'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';
import { shouldHideMarketingChrome } from '@/lib/app-routes';
import { Container } from '@/components/layout/container';
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
    const hideHeader = shouldHideMarketingChrome(pathname);

    // Close mobile menu on route change
    useEffect(() => {
        queueMicrotask(() => setMobileOpen(false));
    }, [pathname]);

    // Prevent body scroll when mobile menu is open
    useEffect(() => {
        window.dispatchEvent(new CustomEvent('re:mobile-menu-state', { detail: { open: mobileOpen } }));
        if (mobileOpen) {
            document.body.style.overflow = 'hidden';
        } else {
            document.body.style.overflow = '';
        }
        return () => {
            document.body.style.overflow = '';
            window.dispatchEvent(new CustomEvent('re:mobile-menu-state', { detail: { open: false } }));
        };
    }, [mobileOpen]);

    const handleToolsEnter = () => {
        if (closeTimeoutRef.current) {
            clearTimeout(closeTimeoutRef.current);
            closeTimeoutRef.current = null;
        }
        setToolsOpen(true);
    };

    const handleToolsLeave = () => {
        if (toolsWrapperRef.current?.contains(document.activeElement)) {
            return;
        }
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
                className="sticky top-0 z-[var(--re-z-nav)] border-b border-[var(--re-nav-border)] bg-[var(--re-nav-bg)] backdrop-blur-[16px] [-webkit-backdrop-filter:blur(16px)]"
            >
                <Container width="marketing" className="flex h-[60px] items-center justify-between gap-3">
                    <Link
                        href="/"
                        className="flex shrink-0 items-center gap-2.5 rounded-sm no-underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-re-focus-ring focus-visible:ring-offset-2 focus-visible:ring-offset-re-ring-offset"
                    >
                        <RegEngineWordmark size="sm" />
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
                </Container>
            </nav>

            <MobileMenu
                user={user}
                showLoggedIn={showLoggedIn}
                pathname={pathname}
                mobileOpen={mobileOpen}
                setMobileOpen={setMobileOpen}
            />

        </>
    );
}
