'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { User } from '@/types/api';
import { apiClient } from './api-client';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';

interface AuthContextType {
  user: User | null;
  accessToken: string | null;
  /** @deprecated API key is no longer exposed to client JS. Use proxy routes instead. */
  apiKey: string | null;
  /** @deprecated Admin key is no longer exposed to client JS. Use proxy routes instead. */
  adminKey: string | null;
  tenantId: string | null;
  isOnboarded: boolean;
  isHydrated: boolean;
  demoMode: boolean;
  setApiKey: (key: string | null) => void;
  setAdminKey: (key: string | null) => void;
  setTenantId: (id: string | null) => void;
  setDemoMode: (enabled: boolean) => void;
  completeOnboarding: () => void;
  clearCredentials: () => void;
  login: (token: string, user: User, tenantId?: string) => Promise<void>;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

/**
 * HTTP-only cookie auth — CRITICAL #2 fix complete.
 *
 * Sensitive credentials (access_token, api_key, admin_key) are stored
 * ONLY in HTTP-only cookies via /api/session. They are never readable
 * by client-side JavaScript, eliminating XSS credential theft.
 *
 * Non-sensitive data (tenant_id, onboarded, demo_mode, user profile)
 * remains in localStorage for fast hydration.
 *
 * The apiKey/adminKey fields in the context are set to a placeholder value
 * ("cookie-managed") to satisfy existing enabled-checks (!!apiKey) without
 * exposing actual secrets.
 */

/** Placeholder value for apiKey/adminKey — indicates credentials are
 *  managed server-side in HTTP-only cookies. NOT the real key. */
const COOKIE_MANAGED_PLACEHOLDER = 'cookie-managed';

const STORAGE_KEYS = {
  TENANT_ID: 'regengine_tenant_id',
  ONBOARDED: 'regengine_onboarded',
  DEMO_MODE: 'regengine_demo_mode',
  USER: 'regengine_user',
  // DEPRECATED — migrated to HTTP-only cookies, then removed from localStorage
  _LEGACY_API_KEY: 'regengine_api_key',
  _LEGACY_ADMIN_KEY: 'regengine_admin_key',
  _LEGACY_ACCESS_TOKEN: 'regengine_access_token',
};

// ---------------------------------------------------------------------------
// Cookie helpers — talk to /api/session (server-side)
// ---------------------------------------------------------------------------

/** Store sensitive credentials in HTTP-only cookies via /api/session POST. */
async function setSessionCookies(params: {
  accessToken?: string | null;
  apiKey?: string | null;
  adminKey?: string | null;
  tenantId?: string | null;
  user?: User | null;
}): Promise<void> {
  if (typeof window === 'undefined') return;
  const body: Record<string, unknown> = {};
  if (params.accessToken) body.access_token = params.accessToken;
  if (params.apiKey) body.api_key = params.apiKey;
  if (params.adminKey) body.admin_key = params.adminKey;
  if (params.tenantId) body.tenant_id = params.tenantId;
  if (params.user) body.user = params.user;
  if (Object.keys(body).length === 0) return;
  try {
    await fetch('/api/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
  } catch {
    // Best-effort
  }
}

/** Clear all session cookies via /api/session DELETE. */
function clearSessionCookies() {
  if (typeof window === 'undefined') return;
  fetch('/api/session', { method: 'DELETE' }).catch(() => {});
}

/** Check current session via /api/session GET — never returns raw tokens. */
async function getSessionInfo(): Promise<{
  authenticated: boolean;
  has_api_key: boolean;
  has_admin_key: boolean;
  has_credentials: boolean;
  tenant_id: string | null;
  user: User | null;
} | null> {
  if (typeof window === 'undefined') return null;
  try {
    const res = await fetch('/api/session', { method: 'GET', credentials: 'include' });
    if (!res.ok) return null;
    return await res.json();
  } catch {
    return null;
  }
}

// ---------------------------------------------------------------------------
// Migration: move localStorage secrets to HTTP-only cookies, then delete them
// ---------------------------------------------------------------------------

async function migrateLocalStorageToCookies(): Promise<void> {
  if (typeof window === 'undefined') return;

  const legacyApiKey = localStorage.getItem(STORAGE_KEYS._LEGACY_API_KEY);
  const legacyAdminKey = localStorage.getItem(STORAGE_KEYS._LEGACY_ADMIN_KEY);
  const legacyAccessToken = localStorage.getItem(STORAGE_KEYS._LEGACY_ACCESS_TOKEN);

  if (!legacyApiKey && !legacyAdminKey && !legacyAccessToken) return;

  console.info('[auth] Migrating credentials from localStorage to HTTP-only cookies...');

  const tenantId = localStorage.getItem(STORAGE_KEYS.TENANT_ID);
  const userStr = localStorage.getItem(STORAGE_KEYS.USER);
  let user: User | null = null;
  try {
    if (userStr) user = JSON.parse(userStr);
  } catch { /* ignore */ }

  await setSessionCookies({
    accessToken: legacyAccessToken,
    apiKey: legacyApiKey,
    adminKey: legacyAdminKey,
    tenantId,
    user,
  });

  // Remove sensitive keys from localStorage permanently
  localStorage.removeItem(STORAGE_KEYS._LEGACY_API_KEY);
  localStorage.removeItem(STORAGE_KEYS._LEGACY_ADMIN_KEY);
  localStorage.removeItem(STORAGE_KEYS._LEGACY_ACCESS_TOKEN);

  console.info('[auth] Migration complete — localStorage secrets removed.');
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [apiKey, setApiKeyState] = useState<string | null>(null);
  const [adminKey, setAdminKeyState] = useState<string | null>(null);
  const [tenantId, setTenantIdState] = useState<string | null>(null);
  const [accessToken, setAccessTokenState] = useState<string | null>(null);
  const [user, setUserState] = useState<User | null>(null);
  const [isOnboarded, setIsOnboarded] = useState(false);
  const [demoMode, setDemoModeState] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);

  // ---- Hydration: migrate localStorage, then hydrate from cookie session ----
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const hydrate = async () => {
      // Step 1: If localStorage still has secrets, migrate them to cookies
      await migrateLocalStorageToCookies();

      // Step 2: Read non-sensitive state from localStorage
      const storedTenantId = localStorage.getItem(STORAGE_KEYS.TENANT_ID);
      const storedOnboarded = localStorage.getItem(STORAGE_KEYS.ONBOARDED);
      const storedDemoMode = localStorage.getItem(STORAGE_KEYS.DEMO_MODE);
      const storedUser = localStorage.getItem(STORAGE_KEYS.USER);

      if (storedTenantId) setTenantIdState(storedTenantId);
      if (storedOnboarded === 'true') setIsOnboarded(true);
      if (storedDemoMode === 'true') setDemoModeState(true);

      if (storedUser) {
        try {
          const parsedUser = JSON.parse(storedUser);
          setUserState(parsedUser);
          apiClient.setUser(parsedUser);
        } catch { /* ignore corrupt data */ }
      }

      // Step 3: Check cookie-based session for credentials
      const session = await getSessionInfo();
      if (session) {
        if (session.tenant_id && !storedTenantId) {
          setTenantIdState(session.tenant_id);
        }
        if (session.user && !storedUser) {
          setUserState(session.user);
          apiClient.setUser(session.user);
        }
        if (session.authenticated) {
          setAccessTokenState(COOKIE_MANAGED_PLACEHOLDER);
          apiClient.setAccessToken(COOKIE_MANAGED_PLACEHOLDER);
        }
        if (session.has_api_key) {
          setApiKeyState(COOKIE_MANAGED_PLACEHOLDER);
        }
        if (session.has_admin_key) {
          setAdminKeyState(COOKIE_MANAGED_PLACEHOLDER);
        }
      } else {
        // No cookie session — user is unauthenticated.
        // NEXT_PUBLIC_API_KEY fallback removed: proxy routes inject
        // server-side API keys; baking secrets into the JS bundle is unsafe.
      }

      setIsHydrated(true);
    };

    hydrate();
  }, []);

  // ---- Supabase auth state listener ----
  useEffect(() => {
    let subscription: { unsubscribe: () => void } | undefined;
    try {
      const supabase = createSupabaseBrowserClient();

      // Use getUser() instead of getSession() — getUser() validates the JWT
      // against the Supabase auth server, while getSession() only reads the
      // local cookie/storage (which can be spoofed).
      supabase.auth.getUser().then(({ data: { user: validatedUser } }) => {
        if (validatedUser && !accessToken) {
          const appUser: User = {
            id: validatedUser.id,
            email: validatedUser.email || '',
            is_sysadmin: validatedUser.user_metadata?.is_sysadmin || false,
            status: 'active',
            role_name: validatedUser.user_metadata?.role || 'member',
          };
          setAccessTokenState(COOKIE_MANAGED_PLACEHOLDER);
          setUserState(appUser);
          apiClient.setAccessToken(COOKIE_MANAGED_PLACEHOLDER);
          apiClient.setUser(appUser);
          if (validatedUser.user_metadata?.tenant_id) {
            setTenantIdState(validatedUser.user_metadata.tenant_id);
            apiClient.setCurrentTenant(validatedUser.user_metadata.tenant_id);
            localStorage.setItem(STORAGE_KEYS.TENANT_ID, validatedUser.user_metadata.tenant_id);
          }
          localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(appUser));
          setSessionCookies({
            accessToken: COOKIE_MANAGED_PLACEHOLDER,
            user: appUser,
            tenantId: validatedUser.user_metadata?.tenant_id || null,
          });
        }
      });

      const { data } = supabase.auth.onAuthStateChange((event, session) => {
        if (session?.access_token && session.user) {
          const appUser: User = {
            id: session.user.id,
            email: session.user.email || '',
            is_sysadmin: session.user.user_metadata?.is_sysadmin || false,
            status: 'active',
            role_name: session.user.user_metadata?.role || 'member',
          };
          setAccessTokenState(COOKIE_MANAGED_PLACEHOLDER);
          setUserState(appUser);
          apiClient.setAccessToken(COOKIE_MANAGED_PLACEHOLDER);
          apiClient.setUser(appUser);
          localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(appUser));
          setSessionCookies({ accessToken: session.access_token, user: appUser });
        }

        if (event === 'SIGNED_OUT') {
          setAccessTokenState(null);
          setUserState(null);
          setApiKeyState(null);
          setAdminKeyState(null);
          apiClient.setAccessToken(null);
          apiClient.setUser(null);
          apiClient.setCurrentTenant(null);
          if (typeof window !== 'undefined') {
            Object.values(STORAGE_KEYS).forEach(key => localStorage.removeItem(key));
          }
          clearSessionCookies();
        }
      });
      subscription = data.subscription;
    } catch {
      // Supabase not configured — skip
    }
    return () => subscription?.unsubscribe();
  }, [accessToken]);

  const setApiKey = useCallback((key: string | null) => {
    if (key) {
      setSessionCookies({ apiKey: key });
      setApiKeyState(COOKIE_MANAGED_PLACEHOLDER);
    } else {
      setApiKeyState(null);
    }
  }, []);

  const setAdminKey = useCallback((key: string | null) => {
    if (key) {
      setSessionCookies({ adminKey: key });
      setAdminKeyState(COOKIE_MANAGED_PLACEHOLDER);
    } else {
      setAdminKeyState(null);
    }
  }, []);

  const setTenantId = useCallback((id: string | null) => {
    setTenantIdState(id);
    if (typeof window !== 'undefined') {
      if (id) {
        localStorage.setItem(STORAGE_KEYS.TENANT_ID, id);
        setSessionCookies({ tenantId: id });
      } else {
        localStorage.removeItem(STORAGE_KEYS.TENANT_ID);
      }
    }
  }, []);

  const setDemoMode = useCallback((enabled: boolean) => {
    setDemoModeState(enabled);
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEYS.DEMO_MODE, String(enabled));
    }
  }, []);

  const completeOnboarding = useCallback(() => {
    setIsOnboarded(true);
    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEYS.ONBOARDED, 'true');
      // Best-effort persist to backend so state survives across devices
      const tid = localStorage.getItem(STORAGE_KEYS.TENANT_ID);
      if (tid) {
        fetch(`/api/admin/v1/tenants/${tid}/settings`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ onboarding: { workspace_setup_completed: true } }),
        }).catch(() => {});
      }
    }
  }, []);

  const login = useCallback(async (token: string, loginUser: User, loginTenantId?: string) => {
    setAccessTokenState(COOKIE_MANAGED_PLACEHOLDER);
    setUserState(loginUser);
    if (loginTenantId) setTenantIdState(loginTenantId);

    apiClient.setAccessToken(COOKIE_MANAGED_PLACEHOLDER);
    apiClient.setUser(loginUser);
    if (loginTenantId) apiClient.setCurrentTenant(loginTenantId);

    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(loginUser));
      if (loginTenantId) localStorage.setItem(STORAGE_KEYS.TENANT_ID, loginTenantId);
    }

    // Store sensitive credentials in HTTP-only cookies.
    // MUST await — middleware checks this cookie on the next navigation.
    await setSessionCookies({
      accessToken: token,
      tenantId: loginTenantId,
      user: loginUser,
    });
  }, []);

  const clearCredentials = useCallback(() => {
    setApiKeyState(null);
    setAdminKeyState(null);
    setTenantIdState(null);
    setAccessTokenState(null);
    setUserState(null);
    setIsOnboarded(false);
    setDemoModeState(false);

    apiClient.setAccessToken(null);
    apiClient.setUser(null);
    apiClient.setCurrentTenant(null);

    if (typeof window !== 'undefined') {
      Object.values(STORAGE_KEYS).forEach(key => localStorage.removeItem(key));
    }
    clearSessionCookies();
  }, []);

  const logout = useCallback(() => {
    clearCredentials();
  }, [clearCredentials]);

  return (
    <AuthContext.Provider
      value={{
        apiKey,
        adminKey,
        tenantId,
        accessToken,
        user,
        isOnboarded,
        isHydrated,
        demoMode,
        setApiKey,
        setAdminKey,
        setTenantId,
        setDemoMode,
        completeOnboarding,
        clearCredentials,
        login,
        logout,
        isAuthenticated: !!(user && accessToken),
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
}
