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
  setApiKey: (key: string | null) => Promise<void>;
  setAdminKey: (key: string | null) => Promise<void>;
  setTenantId: (id: string | null) => Promise<void>;
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

/** Store sensitive credentials in HTTP-only cookies via /api/session POST.
 *  Returns true if the cookie was set successfully, false on failure. */
async function setSessionCookies(params: {
  accessToken?: string | null;
  apiKey?: string | null;
  adminKey?: string | null;
  tenantId?: string | null;
  user?: User | null;
}): Promise<boolean> {
  if (typeof window === 'undefined') return false;
  const body: Record<string, unknown> = {};
  if (params.accessToken) body.access_token = params.accessToken;
  if (params.apiKey) body.api_key = params.apiKey;
  if (params.adminKey) body.admin_key = params.adminKey;
  if (params.tenantId) body.tenant_id = params.tenantId;
  if (params.user) body.user = params.user;
  if (Object.keys(body).length === 0) return true;
  try {
    const res = await fetch('/api/session', {
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

  if (process.env.NODE_ENV !== 'production') {
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
    // If the middleware redirected to /login with an error param, the custom
    // JWT session is dead. Don't let a surviving Supabase session silently
    // re-authenticate — that causes stale nav state where the UI flickers
    // between authenticated and unauthenticated.
    const isAuthErrorRedirect =
      typeof window !== 'undefined' &&
      (window.location.search.includes('error=session_expired') ||
       window.location.search.includes('error=token_invalid'));

    let subscription: { unsubscribe: () => void } | undefined;
    try {
      const supabase = createSupabaseBrowserClient();

      // Use getUser() instead of getSession() — getUser() validates the JWT
      // against the Supabase auth server, while getSession() only reads the
      // local cookie/storage (which can be spoofed).
      supabase.auth.getUser().then(async ({ data: { user: validatedUser } }) => {
        if (isAuthErrorRedirect) return;
        if (validatedUser && !accessToken) {
          const appUser: User = {
            id: validatedUser.id,
            email: validatedUser.email || '',
            is_sysadmin: validatedUser.user_metadata?.is_sysadmin || false,
            status: 'active',
            role_name: validatedUser.user_metadata?.role || 'member',
          };
          // Await cookie write before updating state — ensures middleware
          // sees the cookie before any React re-render triggers navigation.
          await setSessionCookies({
            accessToken: COOKIE_MANAGED_PLACEHOLDER,
            user: appUser,
            tenantId: validatedUser.user_metadata?.tenant_id || null,
          });
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
        }
      });

      const { data } = supabase.auth.onAuthStateChange(async (event, session) => {
        if (isAuthErrorRedirect && event !== 'SIGNED_OUT') return;
        if (session?.access_token && session.user) {
          // Guard: if a custom RegEngine JWT session is already established
          // (accessToken is set), do NOT overwrite re_access_token with the
          // Supabase access_token. The middleware verifies re_access_token
          // using the RegEngine signing key (HS256) — writing a Supabase JWT
          // here would fail verification and trigger a redirect loop.
          //
          // This callback should only bootstrap auth state when the user has
          // a surviving Supabase session but no custom JWT (e.g. page refresh
          // where Supabase cookie persists but re_access_token expired).
          if (accessToken) return;

          const appUser: User = {
            id: session.user.id,
            email: session.user.email || '',
            is_sysadmin: session.user.user_metadata?.is_sysadmin || false,
            status: 'active',
            role_name: session.user.user_metadata?.role || 'member',
          };
          // Await cookie write before updating state — prevents race where
          // middleware rejects requests because cookie isn't set yet.
          await setSessionCookies({ accessToken: session.access_token, user: appUser });
          setAccessTokenState(COOKIE_MANAGED_PLACEHOLDER);
          setUserState(appUser);
          apiClient.setAccessToken(COOKIE_MANAGED_PLACEHOLDER);
          apiClient.setUser(appUser);
          localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(appUser));
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
    // Non-React state — these don't trigger re-renders or effects.
    apiClient.setAccessToken(COOKIE_MANAGED_PLACEHOLDER);
    apiClient.setUser(loginUser);
    if (loginTenantId) apiClient.setCurrentTenant(loginTenantId);

    if (typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEYS.USER, JSON.stringify(loginUser));
      if (loginTenantId) localStorage.setItem(STORAGE_KEYS.TENANT_ID, loginTenantId);
    }

    // Set the HTTP-only cookie BEFORE updating React state.
    //
    // React state updates below trigger a re-render which fires the useEffect
    // in LoginClient. That effect calls getOnboardingStatus and then navigates
    // to /dashboard (or the ?next= path). The middleware runs on that navigation
    // and checks re_access_token — if the cookie isn't in the browser yet,
    // middleware rejects and redirects back to /login?next=/dashboard.
    //
    // Awaiting setSessionCookies first ensures the Set-Cookie response is
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
      user: loginUser,
    });

    if (!cookiesOk) {
      throw new Error('Session could not be established. Please try again.');
    }

    // React state updates — triggers re-renders and the navigation useEffect.
    // Cookie is guaranteed to be stored in the browser at this point.
    setAccessTokenState(COOKIE_MANAGED_PLACEHOLDER);
    setUserState(loginUser);
    if (loginTenantId) setTenantIdState(loginTenantId);
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
    // Sign out from Supabase too — prevents the dual-auth desync where
    // custom JWT cookies are cleared but Supabase session persists,
    // causing the onAuthStateChange listener to silently re-authenticate.
    try {
      const supabase = createSupabaseBrowserClient();
      supabase.auth.signOut().catch(() => {});
    } catch {
      // Supabase not configured — skip
    }
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
