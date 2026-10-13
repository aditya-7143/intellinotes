'use client';

import { ReactNode } from 'react';
import { useAuthStore } from '@/features/auth/authStore';
import { authApi } from '@/lib/api';
import { useEffect } from 'react';

export function Providers({ children }: { children: ReactNode }) {
  const { hydrate, setUser, isAuthenticated, isLoading } = useAuthStore();

  useEffect(() => {
    hydrate();
    const initAuth = async () => {
      if (isAuthenticated && isLoading) {
        try {
          const response = await authApi.getMe();
          setUser(response.data);
        } catch {
          setUser(null);
        }
      }
    };
    initAuth();
  }, [hydrate, setUser, isAuthenticated, isLoading]);

  return <>{children}</>;
}