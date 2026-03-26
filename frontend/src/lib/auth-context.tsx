'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { User } from '@/types/api';
import { apiClient } from './api-client';
import { createSupabaseBrowserClient } from '@/lib/supabase/client';

interface AuthContextType {
  user: User | null;
  accessToken: string | null;
  apiKey: string | null;
  adminKey: string | null;
  tenantId: string | null;
  isOnboarded: boolean;
  isHydrated: boolean;  // Added for hydration tracking
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
 * SECURITY NOTE (CRITICAL #2 — UI Debug Audit 2026-03-19):
 *
 * These localStorage keys are a security risk — any XSS vector can read them.
 * Migration plan:
 *   1. /api/session route now stores api_key + admin_key in HTTP-only cookies
 *   2. /api/proxy route forwards requests using cookie credentials
 *   3. login() and setApiKey()/setAdminKey() dual-write to both localStorage
 *      AND the /api/session HTTP-only cookie endpoint
 *   4. clearCredentials() clears both
 *   5. NEXT STEP: Migrate all apiClient.fetch() calls to use /api/proxy,
 *      then remove API_KEY, ADMIN_KEY, and ACCESS_TOKEN from localStorage entirely
 *
 * MIGRATION PHASE 2: Remove localStorage reads once all clients use cookie-based auth.
 * Currently dual-writing to both localStorage and HTTP-only cookies for backward compatibility.
 * All new code should use /api/proxy instead of direct API calls with localStorage keys.
 */
const STORAGE_KEYS = {
  API_KEY: 'regengine_api_key',
  ADMIN_KEY: 'regengine_admin_key',
  TENANT_ID: 'regengine_tenant_id',
  ONBOARDED: 'regengine_onboarded',
  DEMO_MODE: 'regengine_demo_mode',
  ACCESS_TOKEN: 'regengine_access_token',
  USER: 'regengine_user',
};

/** Sync sensitive credentials to HTTP-only cookies via /api/session.
 *  Returns a promise so callers can await the cookie being set before navigating. */
async function syncSessionCookies(
  accessToken?: string | null,
  apiKey?: string | null,
  adminKey?: string | null,
  tenantId?: string | null,
): Promise<void> {
  if (typeof window === 'undefined') return;
  const body: Record<string, string> = {};
  if (accessToken) body.access_token = accessToken;
  if (apiKey) body.api_key = apiKey;
  if (adminKey) body.admin_key = adminKey;
  if (tenantId) body.tenant_id = tenantId;
  if (Object.keys(body).length > 0) {
    try {
      await fetch('/api/session', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } catch {
      /* best-effort — localStorage is the fallback */
    }
  }
}

/** Clear HTTP-only session cookies */
function clearSessionCookies() {
  if (typeof window === 'undefined') return;
  fetch('/api/session', { method: 'DELETE' }).catch(() => {});
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [apiKey, setApiKeyState] = useState<string | null>(null);
  const [adminKey, setAdminKeyState] = useState<string | null>(null);
  const [tenantId, setTenantIdState] = useState<string | null>(null);
  const [accessToken, setAccessTokenState] = useState<string | null>(null);
  const [user, setUserState] = useState<User | null>(null);
  const [isOnboarded, setIsOnboarded] = useState(false);
  const [demoMode, setDemoModeState] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);

  // Load from localStorage on mount
  useEffect(() => {
    if (typeof window !== 'undefined') {
      const storedApiKey = localStorage.getItem(STORAGE_KEYS.API_KEY);
      const storedAdminKey = localStorage.getItem(STORAGE_KEYS.ADMIN_KEY);
      const storedTenantId = localStorage.getItem(STORAGE_KEYS.TENANT_ID);
      const storedOnboarded = localStorage.getItem(STORAGE_KEYS.ONBOARDED);
      const storedDemoMode = localStorage.getItem(STORAGE_KEYS.DEMO_MODE);
      const storedAccessToken = localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN);
      const storedUser = localStorage.getItem(STORAGE_KEYS.USER);

      // MIGRATION: Warn on localStorage reads for sensitive credentials
      if (storedApiKey) {
        console.warn("[DEPRECATED] Reading API key from localStorage. Migrate to cookie-based auth via /api/proxy.");
        setApiKeyState(storedApiKey);
      }
      if (storedAdminKey) {
        console.warn("[DEPRECATED] Reading admin key from localStorage. Migrate to cookie-based auth via /api/proxy.");
        setAdminKeyState(storedAdminKey);
      }

      // Use stored key or env var (no hardcoded fallback)
      const envKey = process.env.NEXT_PUBLIC_API_KEY || '';
      if (!storedApiKey) setApiKeyState(envKey);
      if (!storedAdminKey) setAdminKeyState(envKey);
      if (storedTenantId) setTenantIdState(storedTenantId);
      if (storedOnboarded === 'true') setIsOnboarded(true);
      if (storedDemoMode === 'true') setDemoModeState(true);

      if (storedAccessToken) {
        setAccessTokenState(storedAccessToken);
        apiClient.setAccessToken(storedAccessToken);
      }
      if (storedUser) {
        try {
          const parsedUser = JSON.parse(storedUser);
          setUserState(parsedUser);
          apiClient.setUser(parsedUser);
        } catch (e) {
          console.error("Failed to parse stored user", e);
        }
      }

      setIsHydrated(true);
    }
  }, []);

  // MIGRATION PHASE 2: Gradual migration from localStorage to cookie-based auth
  // Once cookies are established via /api/session, clear localStorage copies
  useEffect(() => {
    if (typeof window !== 'undefined' && isHydrated) {
      // Check if HTTP-only cookies are set by making a test request to /api/session
      // If successful, clear the localStorage copies of sensitive credentials
      const checkAndMigrate = async () => {
        try {
          const response = await fetch('/api/session', { method: 'GET', credentials: 'include' });
          if (response.ok) {
            const data = await response.json();
            // If cookies exist, safe to remove localStorage copies
            if (data.has_credentials) {
              if (localStorage.getItem(STORAGE_KEYS.API_KEY)) {
                console.info("[MIGRATION] HTTP-only cookies detected. Removing API_KEY from localStorage.");
                localStorage.removeItem(STORAGE_KEYS.API_KEY);
              }
              if (localStorage.getItem(STORAGE_KEYS.ADMIN_KEY)) {
                console.info("[MIGRATION] HTTP-only cookies detected. Removing ADMIN_KEY from localStorage.");
                localStorage.removeItem(STORAGE_KEYS.ADMIN_KEY);
              }
            }
          }
        } catch (e) {
          // /api/session endpoint may not exist yet or server error — skip migration
        }
      };
      checkAndMigrate();
    }
  }, [isHydrated]);

  // Supabase auth state listener — keeps token + user in sync
  useEffect(() => {
    let subscription: { unsubscribe: () => void } | undefined;
    try {
      const supabase = createSupabaseBrowserClient();

      // Hydrate from Supabase session ONLY if no existing credentials
      // (the custom /auth/login flow stores credentials in localStorage,
      // which the first useEffect already loaded)
      supabase.auth.getSession().then(({ data: { session } }) => {
        if (session?.access_token && session.user && !localStorage.getItem(STORAGE_KEYS.ACCESS_TOKEN)) {
          const appUser: User = {
            id: session.user.id,
            email: session.user.email || '',
            is_sysadmin: session.user.user_metadata?.is_sysadmin || false,
            status: 'active',
            role_name: session.user.user_metadata?.role || 'member',
          };
          setAccessTokenState(session.access_token);
          setUserState(appUser);
          apiClient.setAccessToken(session.access_token);
          apiClient.setUser(appUser);
          if (session.user.user_metadata?.tenant_id) {
            setTenantIdState(session.user.user_metadata.tenant_id);
            apiClient.setCurrentTenant(session.user.user_metadata.tenant_id);
          }
          if (typeof window !== 'undefined') {
            localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, session.access_token);
            localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(appUser));
            if (session.user.user_metadata?.tenant_id) {
              localStorage.setItem(STORAGE_KEYS.TENANT_ID, session.user.user_metadata.tenant_id);
            }
          }
        }
      });

      // Listen for auth state changes (token refresh, sign out, etc.)
      const { data } = supabase.auth.onAuthStateChange((event, session) => {
        if (session?.access_token && session.user) {
          const appUser: User = {
            id: session.user.id,
            email: session.user.email || '',
            is_sysadmin: session.user.user_metadata?.is_sysadmin || false,
            status: 'active',
            role_name: session.user.user_metadata?.role || 'member',
          };
          setAccessTokenState(session.access_token);
          setUserState(appUser);
          apiClient.setAccessToken(session.access_token);
          apiClient.setUser(appUser);
          if (typeof window !== 'undefined') {
            localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, session.access_token);
            localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(appUser));
          }
        }

        // Only clear on explicit sign-out — NOT on missing session.
        // The custom /auth/login flow doesn't create Supabase sessions,
        // so INITIAL_SESSION fires with session=null. We must not wipe
        // the valid localStorage-hydrated credentials in that case.
        if (event === 'SIGNED_OUT') {
          setAccessTokenState(null);
          setUserState(null);
          apiClient.setAccessToken(null);
          apiClient.setUser(null);
          apiClient.setCurrentTenant(null);
          if (typeof window !== 'undefined') {
            Object.values(STORAGE_KEYS).forEach(key => localStorage.removeItem(key));
          }
        }
      });
      subscription = data.subscription;
    } catch {
      // Supabase not configured — skip listener (dev/test environments)
    }
    return () => subscription?.unsubscribe();
  }, []);

  const setApiKey = useCallback((key: string | null) => {
    setApiKeyState(key);
    if (typeof window !== 'undefined') {
      if (key) {
        localStorage.setItem(STORAGE_KEYS.API_KEY, key);
        syncSessionCookies(null, key, null, null);
      } else {
        localStorage.removeItem(STORAGE_KEYS.API_KEY);
      }
    }
  }, []);

  const setAdminKey = useCallback((key: string | null) => {
    setAdminKeyState(key);
    if (typeof window !== 'undefined') {
      if (key) {
        localStorage.setItem(STORAGE_KEYS.ADMIN_KEY, key);
        syncSessionCookies(null, null, key, null);
      } else {
        localStorage.removeItem(STORAGE_KEYS.ADMIN_KEY);
      }
    }
  }, []);

  const setTenantId = useCallback((id: string | null) => {
    setTenantIdState(id);
    if (typeof window !== 'undefined') {
      if (id) {
        localStorage.setItem(STORAGE_KEYS.TENANT_ID, id);
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
    }
  }, []);

  const login = useCallback(async (token: string, user: User, tenantId?: string) => {
    setAccessTokenState(token);
    setUserState(user);
    if (tenantId) setTenantIdState(tenantId);

    apiClient.setAccessToken(token);
    apiClient.setUser(user);
    if (tenantId) apiClient.setCurrentTenant(tenantId);

    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEYS.ACCESS_TOKEN, token);
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(user));
      if (tenantId) localStorage.setItem(STORAGE_KEYS.TENANT_ID, tenantId);
    }
    // Dual-write: store access_token + credentials in HTTP-only cookies.
    // MUST await — middleware checks this cookie on the next navigation.
    // Without await, router.push() races ahead and middleware sees no cookie.
    await syncSessionCookies(token, apiKey, adminKey, tenantId);
  }, [apiKey, adminKey]);

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
    // Also clear HTTP-only cookies
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
        isHydrated,  // Expose hydration state
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
