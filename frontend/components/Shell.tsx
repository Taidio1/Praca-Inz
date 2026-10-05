'use client';

import React, { Suspense, useEffect, useState } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { useApp } from '@/lib/store';
import SidebarPortfolioGroups from '@/components/SidebarPortfolioGroups';

type ScreenKey = 'dashboard' | 'portfolio' | 'analysis' | 'feed' | 'sources' | 'settings' | 'asset';

const ROUTES: Record<Exclude<ScreenKey, 'asset'>, string> = {
  dashboard: '/',
  portfolio: '/portfolio',
  analysis: '/analysis',
  feed: '/feed',
  sources: '/sources',
  settings: '/settings',
};

function screenFromPath(path: string): ScreenKey {
  if (path === '/') return 'dashboard';
  if (path.startsWith('/portfolio')) return 'portfolio';
  if (path.startsWith('/analysis')) return 'analysis';
  if (path.startsWith('/feed')) return 'feed';
  if (path.startsWith('/sources')) return 'sources';
  if (path.startsWith('/settings')) return 'settings';
  if (path.startsWith('/asset')) return 'asset';
  return 'dashboard';
}

const SUBS: Record<ScreenKey, string> = {
  dashboard: 'Przegląd wartości i portfela',
  portfolio: 'Śledzono aktywa',
  analysis: 'Wycena i fundamenty popularnych spółek (SEC EDGAR)',
  feed: 'Spersonalizowany strumień informacji',
  asset: 'Pełny widok aktywa z analizą AI',
  sources: 'Ślad filtrowania — audytowalność systemu',
  settings: 'Konfiguracja źródeł i parametrów',
};

function navStyle(active: boolean): React.CSSProperties {
  return {
    display: 'flex',
    alignItems: 'center',
    gap: 12,
    padding: '9px 12px',
    borderRadius: 7,
    border: 'none',
    cursor: 'pointer',
    width: '100%',
    textAlign: 'left',
    background: active ? 'var(--border)' : 'transparent',
    color: active ? 'var(--fg)' : 'var(--fg-2)',
    fontSize: 13.5,
    fontWeight: active ? 600 : 500,
    fontFamily: 'inherit',
    transition: 'background .15s',
  };
}

function NavSection({
  id,
  title,
  open,
  onToggle,
  children,
}: {
  id: string;
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div style={{ marginTop: 18 }}>
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        aria-controls={`nav-section-${id}`}
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          width: '100%',
          padding: '6px 12px',
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          color: 'var(--fg-3)',
          fontSize: 10.5,
          fontWeight: 700,
          letterSpacing: 0.6,
          textTransform: 'uppercase',
        }}
      >
        {title}
        <svg
          width="10"
          height="10"
          viewBox="0 0 10 10"
          fill="currentColor"
          aria-hidden="true"
          style={{ transform: open ? 'none' : 'rotate(180deg)', transition: 'transform .15s' }}
        >
          <path d="M5 2.5L9 7.5H1z" />
        </svg>
      </button>
      {open && (
        <div id={`nav-section-${id}`} style={{ display: 'flex', flexDirection: 'column', gap: 1, marginTop: 4 }}>
          {children}
        </div>
      )}
    </div>
  );
}

const SECTIONS_KEY = 'opes-nav-sections';

function mNavStyle(active: boolean): React.CSSProperties {
  return {
    display: 'flex',
    flexDirection: 'column',
    alignItems: 'center',
    background: 'none',
    border: 'none',
    cursor: 'pointer',
    color: active ? 'var(--accent)' : 'var(--muted-2)',
    padding: '4px 14px',
    fontFamily: 'inherit',
    flex: 1,
  };
}

const M_NAV_ICONS: Record<Exclude<ScreenKey, 'asset'>, React.ReactNode> = {
  dashboard: (
    <svg width="19" height="19" viewBox="0 0 19 19" fill="currentColor">
      <rect x="1" y="1" width="7" height="7" rx="1.5" />
      <rect x="11" y="1" width="7" height="7" rx="1.5" />
      <rect x="1" y="11" width="7" height="7" rx="1.5" />
      <rect x="11" y="11" width="7" height="7" rx="1.5" />
    </svg>
  ),
  portfolio: (
    <svg width="19" height="19" viewBox="0 0 19 19" fill="currentColor">
      <path d="M2 5.5A1.5 1.5 0 013.5 4h12A1.5 1.5 0 0117 5.5v9A1.5 1.5 0 0115.5 16h-12A1.5 1.5 0 012 14.5v-9zm2 1V14h11V6.5H4zm2.5 2.5h6v1.5h-6V9zm0 3h4v1.5h-4V12z" />
    </svg>
  ),
  analysis: (
    <svg width="19" height="19" viewBox="0 0 19 19" fill="currentColor">
      <rect x="2" y="10" width="3.6" height="7" rx="1" />
      <rect x="7.7" y="6" width="3.6" height="11" rx="1" />
      <rect x="13.4" y="2" width="3.6" height="15" rx="1" />
    </svg>
  ),
  feed: (
    <svg width="19" height="19" viewBox="0 0 19 19" fill="currentColor">
      <path d="M2.5 3.5A1.5 1.5 0 014 2h11a1.5 1.5 0 011.5 1.5v12A1.5 1.5 0 0115 17H4a1.5 1.5 0 01-1.5-1.5v-12zM5 5.5h9v1.6H5V5.5zm0 3.5h9v1.6H5V9zm0 3.5h5v1.6H5v-1.6z" />
    </svg>
  ),
  sources: (
    <svg width="19" height="19" viewBox="0 0 19 19" fill="currentColor">
      <path d="M1.5 3.5a1 1 0 011-1h14a1 1 0 010 2h-14a1 1 0 01-1-1zm0 5a1 1 0 011-1h14a1 1 0 010 2h-14a1 1 0 01-1-1zm0 5a1 1 0 011-1h9a1 1 0 010 2h-9a1 1 0 01-1-1z" />
    </svg>
  ),
  settings: (
    <svg width="19" height="19" viewBox="0 0 19 19" fill="currentColor">
      <path
        fillRule="evenodd"
        d="M9.5 2a.5.5 0 01.49.397l.245 1.47c.34.11.662.26.96.443l1.295-.714a.5.5 0 01.63.133l.707.707a.5.5 0 01.133.63l-.714 1.295c.183.298.333.62.443.96l1.47.245A.5.5 0 0115.5 8v1a.5.5 0 01-.397.49l-1.47.245a4.5 4.5 0 01-.443.96l.714 1.295a.5.5 0 01-.133.63l-.707.707a.5.5 0 01-.63.133l-1.295-.714a4.5 4.5 0 01-.96.443l-.245 1.47A.5.5 0 019.5 15h-1a.5.5 0 01-.49-.397l-.245-1.47a4.5 4.5 0 01-.96-.443l-1.295.714a.5.5 0 01-.63-.133l-.707-.707a.5.5 0 01-.133-.63l.714-1.295a4.5 4.5 0 01-.443-.96L2.897 9.49A.5.5 0 012.5 9V8a.5.5 0 01.397-.49l1.47-.245a4.5 4.5 0 01.443-.96l-.714-1.295a.5.5 0 01.133-.63l.707-.707a.5.5 0 01.63-.133l1.295.714a4.5 4.5 0 01.96-.443l.245-1.47A.5.5 0 018.5 2h1zm-.5 5.5a2 2 0 100 4 2 2 0 000-4z"
        clipRule="evenodd"
      />
    </svg>
  ),
};

const NAV_LABELS: Record<Exclude<ScreenKey, 'asset'>, string> = {
  dashboard: 'Dashboard',
  portfolio: 'Portfel',
  analysis: 'Analiza spółek',
  feed: 'Strumień',
  sources: 'Źródła / Audyt',
  settings: 'Ustawienia',
};

const M_NAV_LABELS: Record<Exclude<ScreenKey, 'asset'>, string> = {
  dashboard: 'Dashboard',
  portfolio: 'Portfel',
  analysis: 'Spółki',
  feed: 'Strumień',
  sources: 'Źródła',
  settings: 'Ustawienia',
};

const NAV_KEYS: Exclude<ScreenKey, 'asset'>[] = ['dashboard', 'portfolio', 'analysis', 'feed', 'sources', 'settings'];
const MAIN_NAV_KEYS: Exclude<ScreenKey, 'asset'>[] = ['dashboard', 'portfolio', 'analysis', 'feed'];
const SYSTEM_NAV_KEYS: Exclude<ScreenKey, 'asset'>[] = ['sources', 'settings'];

export default function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { positions, apiOnline, feedConnectionMode, toastVisible, toastMessage, dismissToast } = useApp();

  const [sections, setSections] = useState<Record<string, boolean>>({ portfolios: true, system: true });
  useEffect(() => {
    try {
      const raw = localStorage.getItem(SECTIONS_KEY);
      if (raw) setSections(prev => ({ ...prev, ...(JSON.parse(raw) as Record<string, boolean>) }));
    } catch {}
  }, []);
  const toggleSection = (id: string) =>
    setSections(prev => {
      const next = { ...prev, [id]: !prev[id] };
      try {
        localStorage.setItem(SECTIONS_KEY, JSON.stringify(next));
      } catch {}
      return next;
    });

  const screen = screenFromPath(pathname);
  const analysisTicker = screen === 'analysis' ? pathname.split('/')[2] : undefined;
  const showBackBtn = screen === 'asset' || Boolean(analysisTicker);
  const connectionStatus =
    apiOnline === false
      ? 'API offline'
      : feedConnectionMode === 'live'
        ? 'Feed live'
        : feedConnectionMode === 'polling'
          ? 'Odświeżanie okresowe'
          : apiOnline === true
            ? 'API połączone'
            : 'Sprawdzanie API…';
  const connectionColor =
    apiOnline === false
      ? 'var(--neg)'
      : feedConnectionMode === 'live'
        ? 'var(--pos)'
        : feedConnectionMode === 'polling'
          ? 'var(--accent)'
          : apiOnline === true
            ? 'var(--pos)'
            : 'var(--muted-2)';
  const connectionPulse = feedConnectionMode === 'live';

  let title = 'Opes';
  if (screen === 'asset') {
    const id = pathname.split('/')[2];
    const p = positions.find(x => x.asset.id === id);
    title = p ? `${p.asset.ticker} — ${p.asset.name}` : 'Aktywo';
  } else {
    const titles: Record<Exclude<ScreenKey, 'asset'>, string> = {
      dashboard: 'Dashboard',
      portfolio: 'Portfel',
      analysis: 'Analiza spółek',
      feed: 'Strumień informacji',
      sources: 'Źródła / Audyt',
      settings: 'Ustawienia',
    };
    title = analysisTicker ? `Analiza spółki — ${decodeURIComponent(analysisTicker).toUpperCase()}` : titles[screen];
  }

  return (
    <div
      style={{
        display: 'flex',
        height: '100vh',
        background: 'var(--bg)',
        color: 'var(--fg)',
        overflow: 'hidden',
        position: 'relative',
      }}
    >
      {/* ═══ SIDEBAR (desktop) ═══ */}
      <nav
        data-role="sidebar"
        style={{ width: 240, flexDirection: 'column', background: 'var(--bg-2)', borderRight: '1px solid var(--border)', flexShrink: 0 }}
      >
        <div style={{ padding: '16px 18px 14px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 10 }}>
          <img
            src="/logo.png"
            alt="Opes Logo"
            style={{
              width: 34,
              height: 34,
              borderRadius: 9,
              objectFit: 'cover',
              flexShrink: 0,
              boxShadow: '0 2px 10px rgba(0,255,180,0.15)',
              border: '1px solid var(--border-2)',
            }}
          />
          <div>
            <div style={{ fontWeight: 700, fontSize: 14.5, letterSpacing: -0.4, color: 'var(--fg)' }}>Opes</div>
            <div style={{ fontSize: 9.5, color: 'var(--faint)', fontWeight: 500, letterSpacing: 0.3, marginTop: 1 }}>AI · Informacyjny</div>
          </div>
        </div>

        <div style={{ padding: '7px 18px', borderBottom: '1px solid var(--border)', display: 'flex', alignItems: 'center', gap: 7 }}>
          <div
            style={{
              width: 6,
              height: 6,
              background: connectionColor,
              borderRadius: '50%',
              animation: connectionPulse ? 'pulse 2s infinite' : 'none',
              flexShrink: 0,
            }}
          />
          <span style={{ fontSize: 10.5, color: 'var(--faint)', fontWeight: 500 }}>{connectionStatus}</span>
        </div>

        <div style={{ padding: '12px 10px', flex: 1, display: 'flex', flexDirection: 'column', gap: 1, overflowY: 'auto' }}>
          {MAIN_NAV_KEYS.map(k => (
            <button key={k} type="button" onClick={() => router.push(ROUTES[k])} style={navStyle(screen === k)}>
              <span style={{ color: 'var(--accent)', display: 'flex' }}>{M_NAV_ICONS[k]}</span>
              {NAV_LABELS[k]}
            </button>
          ))}

          <NavSection id="portfolios" title="Portfele" open={sections.portfolios} onToggle={() => toggleSection('portfolios')}>
            <Suspense fallback={null}>
              <SidebarPortfolioGroups />
            </Suspense>
          </NavSection>

          <NavSection id="system" title="System" open={sections.system} onToggle={() => toggleSection('system')}>
            {SYSTEM_NAV_KEYS.map(k => (
              <button key={k} type="button" onClick={() => router.push(ROUTES[k])} style={navStyle(screen === k)}>
                <span style={{ color: 'var(--accent)', display: 'flex' }}>{M_NAV_ICONS[k]}</span>
                {NAV_LABELS[k]}
              </button>
            ))}
          </NavSection>
        </div>

        <div style={{ padding: '10px 16px', borderTop: '1px solid var(--border)' }}>
          <p style={{ fontSize: 9, color: 'var(--faint-2)', lineHeight: 1.5, fontStyle: 'italic' }}>
            Materiał informacyjny i edukacyjny — nie stanowi porady inwestycyjnej.
          </p>
        </div>
      </nav>

      {/* ═══ MAIN ═══ */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden', minWidth: 0 }}>
        {/* Topbar */}
        <header
          style={{
            padding: '11px 16px',
            background: 'var(--bg-2)',
            borderBottom: '1px solid var(--border)',
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            flexShrink: 0,
            zIndex: 10,
          }}
        >
          <img
            src="/logo.png"
            alt="Opes Logo"
            style={{
              width: 28,
              height: 28,
              borderRadius: 7,
              objectFit: 'cover',
              flexShrink: 0,
              border: '1px solid var(--border-2)',
            }}
          />
          {showBackBtn && (
            <button
              type="button"
              onClick={() => router.push(analysisTicker ? '/analysis' : '/')}
              style={{
                background: 'none',
                border: 'none',
                color: 'var(--muted)',
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: 3,
                fontSize: 12,
                padding: 0,
                flexShrink: 0,
                fontFamily: 'inherit',
              }}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="none">
                <path d="M10 4L6 8l4 4" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
              </svg>
              Wróć
            </button>
          )}
          <div style={{ flex: 1, minWidth: 0 }}>
            <h1 style={{ fontSize: 14, fontWeight: 600, color: 'var(--fg)', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
              {title}
            </h1>
            <p style={{ fontSize: 10.5, color: 'var(--muted-2)', marginTop: 1 }}>{SUBS[screen]}</p>
          </div>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 5,
              background: 'var(--panel)',
              border: '1px solid var(--border)',
              borderRadius: 20,
              padding: '4px 10px',
              flexShrink: 0,
            }}
          >
            <div
              style={{
                width: 5,
                height: 5,
                background: connectionColor,
                borderRadius: '50%',
                animation: connectionPulse ? 'pulse 2s infinite' : 'none',
              }}
            />
            <span style={{ fontSize: 10, color: 'var(--faint)', whiteSpace: 'nowrap' }}>{connectionStatus}</span>
          </div>
        </header>

        {/* Content */}
        <div style={{ flex: 1, overflowY: 'auto', paddingBottom: 70 }}>{children}</div>

        {/* ═══ BOTTOM NAV (mobile) ═══ */}
        <nav
          data-role="bottomnav"
          style={{
            position: 'fixed',
            bottom: 0,
            left: 0,
            right: 0,
            background: 'var(--bg-2)',
            borderTop: '1px solid var(--border)',
            padding: '7px 0 14px',
            zIndex: 50,
            flexDirection: 'row',
            justifyContent: 'space-around',
            alignItems: 'center',
          }}
        >
          {NAV_KEYS.map(k => (
            <button key={k} type="button" onClick={() => router.push(ROUTES[k])} style={mNavStyle(screen === k)}>
              {M_NAV_ICONS[k]}
              <span style={{ fontSize: 9, marginTop: 3 }}>{M_NAV_LABELS[k]}</span>
            </button>
          ))}
        </nav>
      </div>

      {/* ═══ TOAST ═══ */}
      {toastVisible && (
        <div
          style={{
            position: 'fixed',
            top: 14,
            right: 14,
            background: 'var(--border)',
            border: '1px solid var(--border-3)',
            borderRadius: 10,
            padding: '11px 14px',
            display: 'flex',
            alignItems: 'center',
            gap: 9,
            zIndex: 1000,
            animation: 'slideIn .3s ease',
            maxWidth: 310,
            boxShadow: '0 8px 32px rgba(0,0,0,.6)',
          }}
        >
          <div style={{ width: 6, height: 6, background: 'var(--pos)', borderRadius: '50%', animation: 'pulse 1.5s infinite', flexShrink: 0 }} />
          <span style={{ fontSize: 12.5, color: 'var(--fg-2)', lineHeight: 1.4, flex: 1 }}>{toastMessage}</span>
          <button
            type="button"
            onClick={dismissToast}
            style={{
              background: 'none',
              border: 'none',
              color: 'var(--muted-2)',
              cursor: 'pointer',
              padding: 0,
              fontSize: 16,
              lineHeight: 1,
              marginLeft: 2,
              fontFamily: 'inherit',
            }}
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}
