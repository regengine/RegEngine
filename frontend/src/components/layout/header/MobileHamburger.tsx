'use client';

interface MobileHamburgerProps {
    mobileOpen: boolean;
    setMobileOpen: (open: boolean) => void;
}

export function MobileHamburger({ mobileOpen, setMobileOpen }: MobileHamburgerProps) {
    return (
        <button
            className="marketing-mobile-toggle"
            onClick={() => setMobileOpen(!mobileOpen)}
            aria-label={mobileOpen ? "Close navigation menu" : "Open navigation menu"}
            aria-expanded={mobileOpen}
            style={{
                background: "transparent",
                border: "1px solid var(--re-mobile-toggle-border)",
                borderRadius: "8px",
                cursor: "pointer",
                color: "var(--re-text-primary)",
                width: "44px",
                height: "44px",
                display: "none",
                alignItems: "center",
                justifyContent: "center",
                padding: 0,
                WebkitTapHighlightColor: "transparent",
                transition: "border-color 0.2s, background 0.2s",
            }}
        >
            {/* Animated hamburger -> X */}
            <svg width="20" height="20" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                <line
                    x1="3" y1={mobileOpen ? "10" : "5"} x2="17" y2={mobileOpen ? "10" : "5"}
                    style={{
                        transition: "all 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
                        transform: mobileOpen ? "rotate(45deg)" : "rotate(0)",
                        transformOrigin: "center",
                    }}
                />
                <line
                    x1="3" y1="10" x2="17" y2="10"
                    style={{
                        transition: "opacity 0.2s",
                        opacity: mobileOpen ? 0 : 1,
                    }}
                />
                <line
                    x1="3" y1={mobileOpen ? "10" : "15"} x2="17" y2={mobileOpen ? "10" : "15"}
                    style={{
                        transition: "all 0.3s cubic-bezier(0.16, 1, 0.3, 1)",
                        transform: mobileOpen ? "rotate(-45deg)" : "rotate(0)",
                        transformOrigin: "center",
                    }}
                />
            </svg>
        </button>
    );
}
