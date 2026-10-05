'use client';

import React, { useEffect, useState } from 'react';
import { useAuth } from '@/lib/auth';

const inputStyle: React.CSSProperties = {
  background: 'var(--border)',
  border: '1px solid var(--border-2)',
  borderRadius: 7,
  padding: '9px 11px',
  color: 'var(--fg)',
  fontSize: 12.5,
  outline: 'none',
  width: '100%',
};

const labelStyle: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 500,
  color: 'var(--muted)',
  marginBottom: 5,
  display: 'block',
};

/* Błąd zwrócony przez OAuth wraca w parametrach URL — pokazujemy go na stronie logowania. */
function oauthErrorFromUrl(): string | null {
  const search = new URLSearchParams(window.location.search);
  const hash = new URLSearchParams(window.location.hash.replace(/^#/, ''));
  const desc = search.get('error_description') || hash.get('error_description');
  return desc ? desc.replace(/\+/g, ' ') : null;
}

export default function LoginPage() {
  const { signInWithPassword, signInWithGoogle } = useAuth();

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [googleLoading, setGoogleLoading] = useState(false);

  useEffect(() => {
    setError(oauthErrorFromUrl());
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (submitting || googleLoading) return;
    setError(null);
    setSubmitting(true);
    const err = await signInWithPassword(email.trim(), password);
    if (err) {
      setError(err);
      setSubmitting(false);
    }
    /* Przy sukcesie przekierowaniem zajmuje się AuthGate. */
  };

  const google = async () => {
    if (submitting || googleLoading) return;
    setError(null);
    setGoogleLoading(true);
    const err = await signInWithGoogle();
    if (err) {
      setError(err);
      setGoogleLoading(false);
    }
  };

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'var(--bg)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 16,
      }}
    >
      <div
        style={{
          width: '100%',
          maxWidth: 360,
          background: 'var(--panel)',
          border: '1px solid var(--border)',
          borderRadius: 12,
          padding: '26px 22px 22px',
          animation: 'fadeUp .3s ease',
        }}
      >
        {/* Logo + nazwa */}
        <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginBottom: 22 }}>
          <img
            src="/logo.png"
            alt="Opes Logo"
            style={{
              width: 48,
              height: 48,
              borderRadius: 12,
              objectFit: 'cover',
              boxShadow: '0 4px 20px rgba(0,255,180,0.2)',
              border: '1px solid var(--border-2)',
              marginBottom: 10,
            }}
          />
          <div style={{ fontWeight: 700, fontSize: 18, letterSpacing: -0.4, color: 'var(--fg)' }}>Opes</div>
          <div style={{ fontSize: 11.5, color: 'var(--muted-2)', marginTop: 3 }}>Zaloguj się, aby przejść do swojego portfela</div>
        </div>

        <form onSubmit={submit}>
          <div style={{ marginBottom: 11 }}>
            <label htmlFor="login-email" style={labelStyle}>
              Adres e-mail
            </label>
            <input
              id="login-email"
              type="email"
              autoComplete="email"
              required
              placeholder="jan@przyklad.pl"
              value={email}
              onChange={e => setEmail(e.target.value)}
              style={inputStyle}
            />
          </div>
          <div style={{ marginBottom: 14 }}>
            <label htmlFor="login-password" style={labelStyle}>
              Hasło
            </label>
            <input
              id="login-password"
              type="password"
              autoComplete="current-password"
              required
              placeholder="••••••••"
              value={password}
              onChange={e => setPassword(e.target.value)}
              style={inputStyle}
            />
          </div>

          {error && (
            <div
              style={{
                background: 'var(--neg-soft)',
                border: '1px solid var(--neg-line)',
                borderRadius: 7,
                padding: '8px 11px',
                fontSize: 11.5,
                color: 'var(--neg)',
                marginBottom: 14,
                lineHeight: 1.45,
                animation: 'fadeUp .2s ease',
              }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={submitting || googleLoading}
            style={{
              width: '100%',
              background: 'linear-gradient(135deg,var(--accent),var(--accent-2))',
              color: 'var(--on-accent)',
              border: 'none',
              borderRadius: 7,
              padding: '10px 16px',
              fontSize: 12.5,
              fontWeight: 600,
              cursor: submitting || googleLoading ? 'default' : 'pointer',
              fontFamily: 'inherit',
              opacity: submitting ? 0.7 : 1,
            }}
          >
            {submitting ? 'Logowanie…' : 'Zaloguj się'}
          </button>
        </form>

        {/* Separator */}
        <div style={{ display: 'flex', alignItems: 'center', gap: 10, margin: '16px 0' }}>
          <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
          <span style={{ fontSize: 10.5, color: 'var(--faint)' }}>albo</span>
          <div style={{ flex: 1, height: 1, background: 'var(--border)' }} />
        </div>

        <button
          type="button"
          onClick={google}
          disabled={submitting || googleLoading}
          style={{
            width: '100%',
            background: 'var(--panel-2)',
            border: '1px solid var(--border-2)',
            color: 'var(--fg-2)',
            borderRadius: 7,
            padding: '10px 16px',
            fontSize: 12.5,
            fontWeight: 500,
            cursor: submitting || googleLoading ? 'default' : 'pointer',
            fontFamily: 'inherit',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 9,
            opacity: googleLoading ? 0.7 : 1,
          }}
        >
          <svg width="15" height="15" viewBox="0 0 18 18">
            <path
              fill="#4285F4"
              d="M17.64 9.2c0-.637-.057-1.251-.164-1.84H9v3.481h4.844a4.14 4.14 0 01-1.796 2.716v2.259h2.908c1.702-1.567 2.684-3.875 2.684-6.615z"
            />
            <path
              fill="#34A853"
              d="M9 18c2.43 0 4.467-.806 5.956-2.18l-2.908-2.259c-.806.54-1.837.86-3.048.86-2.344 0-4.328-1.584-5.036-3.711H.957v2.332A8.997 8.997 0 009 18z"
            />
            <path
              fill="#FBBC05"
              d="M3.964 10.71A5.41 5.41 0 013.682 9c0-.593.102-1.17.282-1.71V4.958H.957A8.997 8.997 0 000 9c0 1.452.348 2.827.957 4.042l3.007-2.332z"
            />
            <path
              fill="#EA4335"
              d="M9 3.58c1.321 0 2.508.454 3.44 1.345l2.582-2.58C13.463.891 11.426 0 9 0A8.997 8.997 0 00.957 4.958L3.964 7.29C4.672 5.163 6.656 3.58 9 3.58z"
            />
          </svg>
          {googleLoading ? 'Przekierowywanie…' : 'Kontynuuj z Google'}
        </button>
      </div>

      <p style={{ fontSize: 10, color: 'var(--faint-2)', marginTop: 18, fontStyle: 'italic', textAlign: 'center', maxWidth: 340, lineHeight: 1.5 }}>
        Materiał informacyjny i edukacyjny — nie stanowi porady inwestycyjnej.
      </p>
    </div>
  );
}
