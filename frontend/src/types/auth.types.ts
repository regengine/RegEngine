/**
 * Authentication Context Type Definitions
 * 
 * Created as part of Platform Audit remediation to eliminate
 * `as any` type violations and provide type safety for auth flows.
 */

export interface User {
    id: string
    email: string
    name?: string
    role: 'admin' | 'analyst' | 'viewer'
    tenantId: string
    createdAt: string
    lastLogin?: string
}

export interface Tenant {
    id: string
    name: string
    slug: string
    createdAt: string
}

export interface Session {
    accessToken: string
    refreshToken: string
    expiresAt: number
    user: User
    tenant: Tenant
}

export interface AuthContextType {
    // State
    user: User | null
    tenant: Tenant | null
    accessToken: string | null
    isAuthenticated: boolean
    isLoading: boolean
    isHydrated: boolean

    // Actions
    login: (email: string, password: string) => Promise<void>
    logout: () => Promise<void>
    switchTenant: (tenantId: string) => Promise<void>
    refreshSession: () => Promise<void>

    // Utilities
    hasPermission: (permission: string) => boolean
    hasRole: (role: User['role']) => boolean
}

export interface AuthProviderProps {
    children: React.ReactNode
}

// Helper type guards
export function isAuthenticated(context: AuthContextType): context is AuthContextType & { user: User; tenant: Tenant } {
    return context.isAuthenticated && context.user !== null && context.tenant !== null
}
