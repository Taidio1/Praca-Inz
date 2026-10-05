'use client';

import React, { createContext, useCallback, useContext, useEffect, useState } from 'react';
import type { Session, User } from '@supabase/supabase-js';
import { supabase } from './supabase';

interface AuthState {
  session: Session | null;
  user: User | null;
  loading: boolean;
  /* Zwracają komunikat błędu (po polsku) albo null przy sukcesie. */
  signInWithPassword: (email: string, password: string) => Promise<string | null>;
  signInWithGoogle: () => Promise<string | null>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthState | null>(null);

function translateAuthError(message: string): string {
  const m = message.toLowerCase();
  if (m.includes('invalid login credentials')) return 'Nieprawidłowy e-mail lub hasło.';
  if (m.includes('email not confirmed')) return 'Adres e-mail nie został potwierdzony.';
  if (m.includes('provider is not enabled') || m.includes('unsupported provider'))
    return 'Logowanie przez Google jest niedostępne — provider nie jest włączony w Supabase.';
  if (m.includes('failed to fetch') || m.includes('network')) return 'Brak połączenia z serwerem uwierzytelniania.';
  return message;
}

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      setSession(data.session);
      setLoading(false);
    });

    const {
      data: { subscription },
    } = supabase.auth.onAuthStateChange((_event, newSession) => {
      setSession(newSession);
      setLoading(false);
    });

    return () => subscription.unsubscribe();
  }, []);

  const signInWithPassword = useCallback(async (email: string, password: string) => {
    const { error } = await supabase.auth.signInWithPassword({ email, password });
    return error ? translateAuthError(error.message) : null;
  }, []);

  const signInWithGoogle = useCallback(async () => {
    const { data, error } = await supabase.auth.signInWithOAuth({
      provider: 'google',
      options: { redirectTo: window.location.origin, skipBrowserRedirect: true },
    });
    if (error) return translateAuthError(error.message);

    /* Sonda przed przekierowaniem: gdy provider nie jest włączony, endpoint /authorize
       zwraca 400 z opisem — pokazujemy czytelny błąd zamiast surowego JSON-a Supabase. */
    try {
      const res = await fetch(data.url, { redirect: 'manual' });
      if (res.status === 400 || res.status === 422) {
        const body = await res.json().catch(() => null);
        return translateAuthError(body?.msg || body?.error_description || 'provider is not enabled');
      }
    } catch {
      /* CORS/sieć — nie blokujemy logowania, przechodzimy do przekierowania. */
    }
    window.location.assign(data.url);
    return null;
  }, []);

  const signOut = useCallback(async () => {
    await supabase.auth.signOut();
  }, []);

  return (
    <AuthContext.Provider
      value={{ session, user: session?.user ?? null, loading, signInWithPassword, signInWithGoogle, signOut }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
