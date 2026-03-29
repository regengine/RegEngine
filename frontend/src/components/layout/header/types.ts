import type { User } from '@/types/api';

/** Shared props for components that need auth-aware nav switching */
export interface AuthNavProps {
    user: User | null;
    showLoggedIn: boolean;
    pathname: string;
}

/** Props for the tools dropdown */
export interface ToolsDropdownProps {
    toolsOpen: boolean;
    setToolsOpen: (open: boolean | ((prev: boolean) => boolean)) => void;
    toolsWrapperRef: React.RefObject<HTMLDivElement>;
    toolsButtonRef: React.RefObject<HTMLButtonElement>;
    handleToolsEnter: () => void;
    handleToolsLeave: () => void;
    handleToolsKeyDown: (e: React.KeyboardEvent<HTMLDivElement>) => void;
    focusFirstToolsItem: () => void;
}

/** Props for the mobile menu */
export interface MobileMenuProps extends AuthNavProps {
    mobileOpen: boolean;
    setMobileOpen: (open: boolean) => void;
}

/** Props for the desktop nav bar */
export interface DesktopNavProps extends AuthNavProps, ToolsDropdownProps {}
