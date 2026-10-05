'use client';

import React, { useState } from 'react';
import { useApp } from '@/lib/store';
import { useAuth } from '@/lib/auth';
import { MONO } from '@/lib/format';
import { BASE_CURRENCIES, currencyInfo } from '@/lib/currency';

const sectionStyle: React.CSSProperties = {
  background: 'var(--panel)',
  border: '1px solid var(--border)',
  borderRadius: 12,
  overflow: 'hidden',
};

const sectionHeader: React.CSSProperties = {
  fontSize: 10,
  fontWeight: 700,
  color: 'var(--muted-2)',
  textTransform: 'uppercase',
  letterSpacing: 0.8,
};

function toggleTrack(on: boolean): React.CSSProperties {
  return {
    width: 36,
    height: 20,
    borderRadius: 10,
    cursor: 'pointer',
    background: on ? 'var(--accent)' : 'var(--border-2)',
    position: 'relative',
    flexShrink: 0,
    border: 'none',
    outline: 'none',
  };
}

function toggleThumb(on: boolean): React.CSSProperties {
  return {
    position: 'absolute',
    top: 2,
    left: on ? 18 : 2,
    width: 16,
    height: 16,
    borderRadius: '50%',
    background: 'white',
    boxShadow: '0 1px 3px rgba(0,0,0,.35)',
    transition: 'left .18s ease',
  };
}

function segStyle(active: boolean): React.CSSProperties {
  return {
    flex: 1,
    padding: '9px 12px',
    borderRadius: 8,
    cursor: 'pointer',
    fontFamily: 'inherit',
    fontSize: 12.5,
    fontWeight: active ? 600 : 500,
    border: 'none',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: 7,
    background: active ? 'var(--accent)' : 'transparent',
    color: active ? 'var(--on-accent)' : 'var(--muted)',
  };
}

export default function SettingsPage() {
  const {
    theme,
    setTheme,
    settingsThreshold,
    setSettingsThreshold,
    settingsNotif,
    toggleNotif,
    settingsLoading,
    baseCurrency,
    setBaseCurrency,
  } = useApp();
  const { user, signOut } = useAuth();
  const [signingOut, setSigningOut] = useState(false);

  const handleSignOut = async () => {
    if (signingOut) return;
    setSigningOut(true);
    await signOut();
    /* Przekierowaniem na /login zajmuje się AuthGate. */
  };

  return (
    <div style={{ padding: '12px 14px', display: 'flex', flexDirection: 'column', gap: 12, maxWidth: 620 }}>
      {/* Konto */}
      <div style={sectionStyle}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
          <div style={sectionHeader}>Konto</div>
        </div>
        <div style={{ padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 12, flexWrap: 'wrap' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--fg-2)' }}>Zalogowano jako</div>
            <div
              style={{
                fontFamily: MONO,
                fontSize: 11.5,
                color: 'var(--muted)',
                marginTop: 2,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {user?.email ?? '—'}
            </div>
          </div>
          <button
            type="button"
            onClick={handleSignOut}
            disabled={signingOut}
            style={{
              background: 'var(--neg-soft)',
              border: '1px solid var(--neg-line)',
              borderRadius: 7,
              padding: '6px 12px',
              color: 'var(--neg)',
              fontSize: 11.5,
              fontWeight: 500,
              cursor: signingOut ? 'default' : 'pointer',
              fontFamily: 'inherit',
              flexShrink: 0,
              opacity: signingOut ? 0.7 : 1,
            }}
          >
            {signingOut ? 'Wylogowywanie…' : 'Wyloguj się'}
          </button>
        </div>
      </div>

      {/* Wygląd */}
      <div style={sectionStyle}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
          <div style={sectionHeader}>Wygląd</div>
        </div>
        <div style={{ padding: '13px 14px' }}>
          <div style={{ marginBottom: 11 }}>
            <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--fg-2)' }}>Motyw kolorystyczny</div>
            <div style={{ fontSize: 11, color: 'var(--muted-2)', marginTop: 2 }}>Przełącz między trybem ciemnym a jasnym</div>
          </div>
          <div style={{ display: 'flex', gap: 6, background: 'var(--bg-inset)', border: '1px solid var(--border)', borderRadius: 10, padding: 4 }}>
            <button type="button" onClick={() => setTheme('dark')} style={segStyle(theme === 'dark')}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <path d="M11.6 8.3A4.7 4.7 0 015.7 2.4 4.7 4.7 0 1011.6 8.3z" stroke="currentColor" strokeWidth="1.3" strokeLinejoin="round" />
              </svg>
              Ciemny
            </button>
            <button type="button" onClick={() => setTheme('light')} style={segStyle(theme === 'light')}>
              <svg width="14" height="14" viewBox="0 0 14 14" fill="none">
                <circle cx="7" cy="7" r="2.7" stroke="currentColor" strokeWidth="1.3" />
                <path
                  d="M7 1v1.5M7 11.5V13M1 7h1.5M11.5 7H13M2.9 2.9l1 1M10.1 10.1l1 1M11.1 2.9l-1 1M3.9 10.1l-1 1"
                  stroke="currentColor"
                  strokeWidth="1.3"
                  strokeLinecap="round"
                />
              </svg>
              Jasny
            </button>
          </div>
        </div>
      </div>

      {/* Waluta bazowa — zapis do backendu (PUT /settings, pole base_currency) */}
      <div style={sectionStyle}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
          <div style={sectionHeader}>Waluta</div>
        </div>
        <div style={{ padding: '13px 14px', opacity: settingsLoading ? 0.5 : 1 }}>
          <div style={{ marginBottom: 11 }}>
            <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--fg-2)' }}>Waluta bazowa portfela</div>
            <div style={{ fontSize: 11, color: 'var(--muted-2)', marginTop: 2 }}>
              Sumy, wartości i wynik liczone w tej walucie: bieżąca wartość po dzisiejszym kursie, koszt po kursie
              z dnia zakupu (NBP).
            </div>
          </div>
          <div
            role="radiogroup"
            aria-label="Waluta bazowa portfela"
            style={{ display: 'flex', gap: 6, background: 'var(--bg-inset)', border: '1px solid var(--border)', borderRadius: 10, padding: 4 }}
          >
            {BASE_CURRENCIES.map(code => (
              <button
                key={code}
                type="button"
                role="radio"
                aria-checked={baseCurrency === code}
                disabled={settingsLoading}
                onClick={() => {
                  if (code !== baseCurrency) void setBaseCurrency(code);
                }}
                style={segStyle(baseCurrency === code)}
              >
                <span style={{ fontFamily: MONO, fontWeight: 700 }}>{currencyInfo(code).symbol}</span>
                {code}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Filtry trafności — zapis do backendu (PUT /settings) */}
      <div style={sectionStyle}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
          <div style={sectionHeader}>Filtry trafności</div>
        </div>
        <div style={{ padding: '13px 14px', opacity: settingsLoading ? 0.5 : 1 }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 9 }}>
            <div>
              <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--fg-2)' }}>Próg trafności źródła</div>
              <div style={{ fontSize: 11, color: 'var(--muted-2)', marginTop: 2 }}>Minimalna trafność do uwzględnienia w analizie</div>
            </div>
            <span style={{ fontFamily: MONO, fontSize: 16, fontWeight: 700, color: 'var(--accent)' }}>
              {settingsLoading ? '…' : settingsThreshold.toFixed(2)}
            </span>
          </div>
          <input
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={settingsThreshold}
            disabled={settingsLoading}
            onChange={e => setSettingsThreshold(parseFloat(e.target.value))}
            style={{ width: '100%', accentColor: 'var(--accent)', cursor: 'pointer' }}
          />
          <div style={{ display: 'flex', justifyContent: 'space-between', marginTop: 3 }}>
            <span style={{ fontSize: 9.5, color: 'var(--faint)' }}>0.00 — wszystko</span>
            <span style={{ fontSize: 9.5, color: 'var(--faint)' }}>1.00 — tylko pewne</span>
          </div>
        </div>
      </div>

      {/* Powiadomienia — zapis do backendu (PUT /settings, pole notifications) */}
      <div style={sectionStyle}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
          <div style={sectionHeader}>Powiadomienia PWA</div>
        </div>
        <div style={{ padding: '12px 14px', display: 'flex', alignItems: 'center', gap: 12, opacity: settingsLoading ? 0.5 : 1 }}>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 13.5, fontWeight: 500, color: 'var(--fg-2)' }}>Powiadomienia push</div>
            <div style={{ fontSize: 11, color: 'var(--muted-2)', marginTop: 2 }}>Informuj o nowych istotnych wydarzeniach</div>
          </div>
          <div onClick={settingsLoading ? undefined : toggleNotif} style={toggleTrack(settingsNotif)}>
            <div style={toggleThumb(settingsNotif)} />
          </div>
        </div>
      </div>

      {/* Konfiguracja silnika — poza zakresem ustawień użytkownika */}
      <div style={sectionStyle}>
        <div style={{ padding: '10px 14px', borderBottom: '1px solid var(--border)' }}>
          <div style={sectionHeader}>Konfiguracja silnika</div>
        </div>
        <div style={{ padding: '12px 14px' }}>
          <p style={{ fontSize: 11.5, color: 'var(--muted-2)', lineHeight: 1.6 }}>
            Dostawca LLM, interwał odświeżania analizy, źródła newsowe (GDELT / RSS / Gemini) i klucze API są konfiguracją silnika
            zbierania danych — ustawiane w pliku <span style={{ fontFamily: MONO }}>.env</span> backendu
            (<span style={{ fontFamily: MONO }}>LLM_PROVIDER</span>, <span style={{ fontFamily: MONO }}>ANALYSIS_INTERVAL_SECONDS</span>,{' '}
            <span style={{ fontFamily: MONO }}>GDELT_ENABLED</span>, <span style={{ fontFamily: MONO }}>RSS_FEEDS</span>), nie z poziomu
            aplikacji.
          </p>
        </div>
      </div>

      {/* Disclaimer */}
      <div style={{ background: 'var(--bg-3)', border: '1px solid var(--border)', borderRadius: 10, padding: '13px 14px' }}>
        <p style={{ fontSize: 10.5, color: 'var(--faint)', lineHeight: 1.6, fontStyle: 'italic' }}>
          ⚠ Opes jest narzędziem informacyjnym i edukacyjnym. Nie rekomenduje transakcji, nie składa zleceń, nie przewiduje ceny. System
          informuje — człowiek interpretuje. Wszelkie decyzje inwestycyjne należą wyłącznie do użytkownika.
        </p>
      </div>
    </div>
  );
}
