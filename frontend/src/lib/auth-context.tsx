'use client';

import React, { createContext, useContext, useState, useEffect, useCallback, useRef } from 'react';
import type { User, SessionAuthMethod } from '@/types/api';
import { apiClient } from './api-client';
import { fetchWithCsrf } from './fetch-with-csrf';
import { sanitizePermissions } from './permissions';

interface AuthContextType {
  user: User | null;
  accessToken: string | null;
  /** @deprecated Use hasTenantSession or hasAdminSession instead. */
  apiKey: string | null;
  /** @deprecated Use hasAdminSession instead. */
  adminKey: string | null;
  tenantId: string | null;
  hasTenantSession: boolean;
  hasAdminSession: boolean;
  authMethod: SessionAuthMethod | null;
  isHighAssuranceSession: boolean;
  isOnboarded: boolean;
  isHydrated: boolean;
  demoMode: boolean;
  setApiKey: (key: string | null) => Promise<void>;
  setAdminKey: (key: string | null) => Promise<void>;
  setTenantId: (id: string | null) => Promise<void>;
  setDemoMode: (enabled: boolean) => void;
  completeOnboarding: () => void;
  clearCredentials: () => Promise<void>;
  login: (token: string, user: User, tenantId?: string, options?: LoginOptions) => Promise<void>;
  logout: () => Promise<void>;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

type LoginOptions = {
  remember?: boolean;
};

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
 * The apiKey/adminKey fields in the context are still set to a placeholder
 * value ("cookie-managed") for transitional compatibility. New code should
 * gate on hasTenantSession / hasAdminSession instead of placeholder secrets.
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

/** Store sensitive credentials in HTTP-only cookies via /api/session POST.
 *  Returns true if the cookie was set successfully, false on failure. */
async function setSessionCookies(params: {
  accessToken?: string | null;
  apiKey?: string | null;
  adminKey?: string | null;
  tenantId?: string | null;
  user?: User | null;
  remember?: boolean;
}): Promise<boolean> {
  if (typeof window === 'undefined') return false;
  const body: Record<string, unknown> = {};
  if (params.accessToken) body.access_token = params.accessToken;
  if (params.apiKey) body.api_key = params.apiKey;
  if (params.adminKey) body.admin_key = params.adminKey;
  if (params.tenantId) body.tenant_id = params.tenantId;
  if (params.user) body.user = params.user;
  if (Object.keys(body).length === 0) return true;
  body.remember_me = params.remember ?? true;
  try {
    // CSRF bootstrap: /api/session is no longer exempt from the CSRF
    // double-submit check, so this POST needs a valid X-CSRF-Token header.
    // GET /api/session is idempotent and sets the cookie pair on first
    // call. The auth provider runs this on mount, but on cold-start /
    // SSR'd login pages the hydrate effect may not have fired yet — call
    // bootstrap defensively here so a freshly-loaded login page can submit
    // immediately without race-conditioning on the hydrate fetch.
    if (!document.cookie.includes('re_csrf=')) {
      try {
        await fetch('/api/session', { method: 'GET', credentials: 'include' });
      } catch { /* fall through — POST will surface the error if cookies still missing */ }
    }
    const res = await fetchWithCsrf('/api/session', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    if (!res.ok) {
      if (process.env.NODE_ENV !== 'production') {
        console.error('[auth] Failed to set session cookie:', res.status);
      }
      return false;
    }
    return true;
  } catch (err) {
    if (process.env.NODE_ENV !== 'production') {
      console.error('[auth] Failed to set session cookie:', err);
    }
    return false;
  }
}

/** Clear all session cookies via /api/session DELETE. Must be awaited before navigation. */
async function clearSessionCookies(): Promise<void> {
  if (typeof window === 'undefined') return;
  try {
    const res = await fetchWithCsrf('/api/session', { method: 'DELETE' });
    if (!res.ok && process.env.NODE_ENV !== 'production') {
      console.error('[auth] Failed to clear session cookie:', res.status);
    }
  } catch (err) {
    if (process.env.NODE_ENV !== 'production') {
      console.error('[auth] Failed to clear session cookie:', err);
    }
  }
}

/** Check current session via /api/session GET — never returns raw tokens. */
async function getSessionInfo(): Promise<{
  authenticated: boolean;
  has_api_key: boolean;
  has_admin_key: boolean;
  has_credentials: boolean;
  tenant_id: string | null;
  user: User | null;
  auth_method?: SessionAuthMethod | null;
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

function normalizeUserProfile(user: User | null | undefined): User | null {
  if (!user) return null;

  return {
    ...user,
    permissions: sanitizePermissions(user.permissions),
  };
}

function normalizeAuthMethod(value: unknown): SessionAuthMethod | null {
  if (value === 'email_otp' || value === 'webauthn' || value === 'sso') {
    return value;
  }
  return null;
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

  if (process.env.NODE_ENV !== 'production') {
    // eslint-disable-next-line no-console
    console.info('[auth] Migrating credentials from localStorage to HTTP-only cookies...');
  }
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

  if (process.env.NODE_ENV !== 'production') {
    // eslint-disable-next-line no-console
    console.info('[auth] Migration complete — localStorage secrets removed.');
  }
}

// ---------------------------------------------------------------------------
// Provider
// ---------------------------------------------------------------------------

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [apiKey, setApiKeyState] = useState<string | null>(null);
  const [adminKey, setAdminKeyState] = useState<string | null>(null);
  const [tenantId, setTenantIdState] = useState<string | null>(null);
  const [accessToken, setAccessTokenState] = useState<string | null>(null);
  const [authMethod, setAuthMethodState] = useState<SessionAuthMethod | null>(null);
  const [user, setUserState] = useState<User | null>(null);
  const [isOnboarded, setIsOnboarded] = useState(false);
  const [demoMode, setDemoModeState] = useState(false);
  const [isHydrated, setIsHydrated] = useState(false);
  const logoutInProgressRef = useRef(false);

  // ---- Hydration: migrate localStorage, then hydrate from cookie session ----
  useEffect(() => {
    if (typeof window === 'undefined') return;

    const hydrate = async () => {
      // If middleware redirected here with an auth error the JWT is expired or
      // invalid. Clear stale client state so the nav doesn't render an
      // authenticated shell on the login page.
      const isAuthError =
        window.location.search.includes('error=session_expired') ||
        window.location.search.includes('error=token_invalid');

      if (isAuthError) {
        Object.values(STORAGE_KEYS).forEach(key => localStorage.removeItem(key));
        clearSessionCookies();
        setAuthMethodState(null);
        setIsHydrated(true);
        return;
      }

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
          const parsedUser = normalizeUserProfile(JSON.parse(storedUser) as User);
          setUserState(parsedUser);
          apiClient.setUser(parsedUser);
        } catch { /* ignore corrupt data */ }
      }

      // Step 3: Check cookie-based session for credentials
      const session = await getSessionInfo();
      if (session) {
        const sessionAuthMethod = normalizeAuthMethod(session.auth_method);
        setAuthMethodState(sessionAuthMethod);
        if (session.tenant_id && session.tenant_id !== storedTenantId) {
          setTenantIdState(session.tenant_id);
          localStorage.setItem(STORAGE_KEYS.TENANT_ID, session.tenant_id);
        } else if (!session.tenant_id && session.auth_method && storedTenantId) {
          setTenantIdState(null);
          localStorage.removeItem(STORAGE_KEYS.TENANT_ID);
        }
        if (session.user) {
          const normalizedSessionUser = normalizeUserProfile(session.user);
          setUserState(normalizedSessionUser);
          apiClient.setUser(normalizedSessionUser);
          localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(normalizedSessionUser));
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
        setAuthMethodState(null);
      }

      setIsHydrated(true);
    };

    hydrate();
  }, []);

  const setApiKey = useCallback(async (key: string | null) => {
    if (key) {
      // MUST await — middleware checks this cookie on the next request.
      // Setting state before the cookie is written causes a race condition
      // where the app appears authenticated but middleware rejects the request.
      await setSessionCookies({ apiKey: key });
      setApiKeyState(COOKIE_MANAGED_PLACEHOLDER);
    } else {
      setApiKeyState(null);
    }
  }, []);

  const setAdminKey = useCallback(async (key: string | null) => {
    if (key) {
      // MUST await — see setApiKey comment.
      await setSessionCookies({ adminKey: key });
      setAdminKeyState(COOKIE_MANAGED_PLACEHOLDER);
    } else {
      setAdminKeyState(null);
    }
  }, []);

  const setTenantId = useCallback(async (id: string | null) => {
    if (typeof window !== 'undefined') {
      if (id) {
        // Await cookie write before updating state — middleware needs the
        // tenant cookie in place before any navigation triggers a request.
        await setSessionCookies({ tenantId: id });
        localStorage.setItem(STORAGE_KEYS.TENANT_ID, id);
      } else {
        localStorage.removeItem(STORAGE_KEYS.TENANT_ID);
      }
    }
    setTenantIdState(id);
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
        fetchWithCsrf(`/api/admin/v1/tenants/${tid}/settings`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify({ onboarding: { workspace_setup_completed: true } }),
        }).catch(() => {});
      }
    }
  }, []);

  const login = useCallback(async (
    token: string,
    loginUser: User,
    loginTenantId?: string,
    options?: LoginOptions,
  ) => {
    logoutInProgressRef.current = false;
    const normalizedLoginUser = normalizeUserProfile(loginUser);

    // Non-React state — these don't trigger re-renders or effects.
    apiClient.setAccessToken(COOKIE_MANAGED_PLACEHOLDER);
    apiClient.setUser(normalizedLoginUser);
    if (loginTenantId) apiClient.setCurrentTenant(loginTenantId);

    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(normalizedLoginUser));
      if (loginTenantId) localStorage.setItem(STORAGE_KEYS.TENANT_ID, loginTenantId);
    }

    // Set the HTTP-only cookie BEFORE updating React state.
    //
    // React state updates below can trigger navigation to /dashboard (or the
    // ?next= path). The middleware runs on that navigation and checks
    // re_access_token — if the cookie isn't in the browser yet, middleware
    // rejects and redirects back to /login?next=/dashboard.
    //
    // Awaiting setSessionCookies first lets the Set-Cookie response be
    // processed by the browser before any navigation can occur.
    //
    // #535: Check the return value — if the /api/session POST fails (network
    // error, server error) we must throw rather than silently continue.
    // A false return means the re_access_token cookie was never written, so
    // the very next middleware check would reject the user and redirect back
    // to /login, producing a confusing loop. Throwing here surfaces the
    // problem immediately as an error in the login form instead.
    const cookiesOk = await setSessionCookies({
      accessToken: token,
      tenantId: loginTenantId,
      user: normalizedLoginUser,
      remember: options?.remember ?? true,
    });

    if (!cookiesOk) {
      throw new Error('Session could not be established. Please try again.');
    }

    // React state updates — triggers re-renders and the navigation useEffect.
    // Cookie should be stored in the browser at this point.
    setAccessTokenState(COOKIE_MANAGED_PLACEHOLDER);
    setAuthMethodState(null);
    setUserState(normalizedLoginUser);
    if (loginTenantId) setTenantIdState(loginTenantId);
  }, []);

  const clearCredentials = useCallback(async () => {
    setApiKeyState(null);
    setAdminKeyState(null);
    setTenantIdState(null);
    setAccessTokenState(null);
    setAuthMethodState(null);
    setUserState(null);
    setIsOnboarded(false);
    setDemoModeState(false);

    apiClient.setAccessToken(null);
    apiClient.setUser(null);
    apiClient.setCurrentTenant(null);

    if (typeof window !== 'undefined') {
      Object.values(STORAGE_KEYS).forEach(key => localStorage.removeItem(key));
    }
    await clearSessionCookies();
  }, []);

  const logout = useCallback(async () => {
    logoutInProgressRef.current = true;
    await clearCredentials();
    logoutInProgressRef.current = false;
  }, [clearCredentials]);

  const isAuthenticated = !!(user && accessToken);
  const normalizedRoleName = user?.role_name?.toLowerCase() ?? null;
  const hasTenantSession = isAuthenticated && !!tenantId;
  const hasAdminSession = Boolean(
    adminKey ||
    user?.is_sysadmin ||
    normalizedRoleName === 'admin' ||
    normalizedRoleName === 'owner',
  );
  const isHighAssuranceSession = authMethod === 'webauthn' || authMethod === 'sso';

  return (
    <AuthContext.Provider
      value={{
        apiKey,
        adminKey,
        tenantId,
        hasTenantSession,
        hasAdminSession,
        authMethod,
        isHighAssuranceSession,
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
        isAuthenticated,
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
