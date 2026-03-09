'use client';

import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import { User } from '@/types/api';
import { apiClient } from './api-client';

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
  login: (token: string, user: User, tenantId?: string) => void;
  logout: () => void;
  isAuthenticated: boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const STORAGE_KEYS = {
  API_KEY: 'regengine_api_key',
  ADMIN_KEY: 'regengine_admin_key',
  TENANT_ID: 'regengine_tenant_id',
  ONBOARDED: 'regengine_onboarded',
  DEMO_MODE: 'regengine_demo_mode',
  ACCESS_TOKEN: 'regengine_access_token',
  USER: 'regengine_user',
};

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

      // Use stored key or env var (no hardcoded fallback)
      const envKey = process.env.NEXT_PUBLIC_API_KEY || '';
      setApiKeyState(storedApiKey || envKey);
      setAdminKeyState(storedAdminKey || envKey);
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

  const setApiKey = useCallback((key: string | null) => {
    setApiKeyState(key);
    if (typeof window !== 'undefined') {
      if (key) {
        localStorage.setItem(STORAGE_KEYS.API_KEY, key);
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

  const login = useCallback((token: string, user: User, tenantId?: string) => {
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
  }, []);

  const logout = useCallback(() => {
    clearCredentials();
  }, [clearCredentials]);

  // Don't render children until hydrated to prevent hydration mismatch
  if (!isHydrated) {
    return null;
  }

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
        isAuthenticated: !!user && !!accessToken,
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
