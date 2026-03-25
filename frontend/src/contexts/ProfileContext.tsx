import { createContext, useContext } from 'react';
import type { ReactNode } from 'react';
import type { UserProfile } from '../types';

interface ProfileContextValue {
  profile: UserProfile | null;
  updateProfile: (updates: Partial<UserProfile>) => void;
  logout: () => Promise<void>;
}

const ProfileContext = createContext<ProfileContextValue | null>(null);

export function ProfileProvider({
  profile,
  updateProfile,
  logout,
  children,
}: ProfileContextValue & { children: ReactNode }) {
  return (
    <ProfileContext.Provider value={{ profile, updateProfile, logout }}>
      {children}
    </ProfileContext.Provider>
  );
}

export function useProfileContext(): ProfileContextValue {
  const ctx = useContext(ProfileContext);
  if (!ctx) {
    throw new Error('useProfileContext must be used within a ProfileProvider');
  }
  return ctx;
}
