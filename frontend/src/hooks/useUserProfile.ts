import { useState, useCallback } from 'react';
import type { UserProfile } from '../types';

const STORAGE_KEY = 'avni-ai-user-profile';

function loadProfile(): UserProfile | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

function saveProfileLocal(profile: UserProfile) {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(profile));
}

export function useUserProfile() {
  const [profile, setProfile] = useState<UserProfile | null>(loadProfile);

  const login = useCallback(async (data: {
    email: string;
    password: string;
    name: string;
    orgName: string;
    sector: string;
    orgContext: string;
    isRegister: boolean;
  }) => {
    const endpoint = data.isRegister ? '/api/auth/register' : '/api/auth/login';
    const body = data.isRegister
      ? {
          email: data.email,
          password: data.password,
          name: data.name,
          org_name: data.orgName,
          sector: data.sector,
          org_context: data.orgContext,
        }
      : {
          email: data.email,
          password: data.password,
        };

    const response = await fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });

    if (!response.ok) {
      const err = await response.json().catch(() => ({ detail: 'Request failed' }));
      throw new Error(err.detail || `${response.status} ${response.statusText}`);
    }

    const result = await response.json();
    const user = result.user;

    const p: UserProfile = {
      id: user.id,
      name: user.name || data.name,
      email: user.email || data.email,
      orgName: user.org_name || data.orgName,
      sector: user.sector || data.sector,
      orgContext: user.org_context || data.orgContext,
      role: user.role || 'implementor',
      isActive: user.is_active !== undefined ? user.is_active : true,
      createdAt: user.created_at || new Date().toISOString(),
      accessToken: result.access_token,
      refreshToken: result.refresh_token,
    };

    saveProfileLocal(p);
    setProfile(p);
  }, []);

  const updateProfile = useCallback(async (updates: Partial<Pick<UserProfile, 'orgName' | 'sector' | 'orgContext'>>) => {
    setProfile(prev => {
      if (!prev) return prev;
      const updated = { ...prev };
      if (updates.orgName !== undefined) updated.orgName = updates.orgName.trim();
      if (updates.sector !== undefined) updated.sector = updates.sector.trim();
      if (updates.orgContext !== undefined) updated.orgContext = updates.orgContext.trim();
      saveProfileLocal(updated);
      return updated;
    });
  }, []);

  const logout = useCallback(async () => {
    // Call backend to revoke all refresh tokens before clearing local state
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (raw) {
        const stored = JSON.parse(raw);
        if (stored.accessToken) {
          await fetch('/api/auth/logout', {
            method: 'POST',
            headers: { Authorization: `Bearer ${stored.accessToken}` },
          });
        }
      }
    } catch {
      // Ignore errors — we still want to clear local state even if the server call fails
    }
    localStorage.removeItem(STORAGE_KEY);
    setProfile(null);
  }, []);

  return { profile, login, updateProfile, logout };
}
