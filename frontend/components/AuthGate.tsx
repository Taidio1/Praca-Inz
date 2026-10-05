'use client';

import React, { useEffect } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth';
import Shell from '@/components/Shell';

/* Pełnoekranowy stan przejściowy — podczas odczytu sesji i przekierowań. */
function Splash() {
  return (
    <div
      style={{
        height: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: 'var(--bg)',
      }}
    >
      <div
        style={{
          width: 40,
          height: 40,
          background: 'linear-gradient(135deg,var(--accent),var(--accent-2))',
          borderRadius: 10,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          color: 'var(--on-accent)',
          boxShadow: '0 4px 14px var(--accent-glow)',
          animation: 'pulse 1.5s infinite',
        }}
      >
        <svg width="20" height="20" viewBox="0 0 16 16" fill="none">
          <path d="M2 13L5.5 5.5L9.5 9L14 3" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </div>
    </div>
  );
}

export default function AuthGate({ children }: { children: React.ReactNode }) {
  const { session, loading } = useAuth();
  const pathname = usePathname();
  const router = useRouter();
  const isLoginPage = pathname === '/login';

  useEffect(() => {
    if (loading) return;
    if (!session && !isLoginPage) router.replace('/login');
    if (session && isLoginPage) router.replace('/');
  }, [loading, session, isLoginPage, router]);

  if (loading || (!session && !isLoginPage) || (session && isLoginPage)) return <Splash />;

  /* /login renderuje się bez Shell-a (bez sidebara i dolnej nawigacji). */
  if (isLoginPage) return <>{children}</>;

  return <Shell>{children}</Shell>;
}
