'use client';

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { useAuth } from './auth';
import * as api from './api';
import { ApiError } from './api';
import type { AssetType, BaseCurrency, PhysicalForm, PortfolioPosition } from './types';

export type FeedConnectionMode = 'idle' | 'live' | 'polling';

interface AppState {
  theme: 'dark' | 'light';
  setTheme: (m: 'dark' | 'light') => void;

  positions: PortfolioPosition[];
  portfolioLoading: boolean;
  portfolioError: string | null;
  refreshPortfolio: () => Promise<void>;
  addAsset: (
    ticker: string,
    type: AssetType,
    qty: number,
    price: number,
    purchasedAt: string,
    currency: string | null,
    physicalForm?: PhysicalForm | null,
  ) => Promise<boolean>;
  removeAsset: (positionId: string) => Promise<void>;

  settingsThreshold: number;
  setSettingsThreshold: (v: number) => void;
  settingsNotif: boolean;
  toggleNotif: () => void;
  baseCurrency: BaseCurrency;
  setBaseCurrency: (c: BaseCurrency) => Promise<void>;
  settingsLoading: boolean;

  apiOnline: boolean | null;
  feedConnectionMode: FeedConnectionMode;
  setFeedConnectionMode: (mode: FeedConnectionMode) => void;

  toastVisible: boolean;
  toastMessage: string;
  showToast: (msg: string) => void;
  dismissToast: () => void;

  isMobile: boolean;
}

const AppContext = createContext<AppState | null>(null);

export function AppProvider({ children }: { children: React.ReactNode }) {
  const { session } = useAuth();
  const [theme, setThemeState] = useState<'dark' | 'light'>('dark');

  const [positions, setPositions] = useState<PortfolioPosition[]>([]);
  const [portfolioLoading, setPortfolioLoading] = useState(true);
  const [portfolioError, setPortfolioError] = useState<string | null>(null);

  const [settingsThreshold, setThresholdState] = useState(0.5);
  const [settingsNotif, setSettingsNotif] = useState(true);
  const [baseCurrency, setBaseCurrencyState] = useState<BaseCurrency>('PLN');
  const [settingsLoading, setSettingsLoading] = useState(true);
  const thresholdSaveTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [apiOnline, setApiOnline] = useState<boolean | null>(null);
  const [feedConnectionMode, setFeedConnectionMode] = useState<FeedConnectionMode>('idle');

  const [toastVisible, setToastVisible] = useState(false);
  const [toastMessage, setToastMessage] = useState('');
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const [isMobile, setIsMobile] = useState(false);

  useEffect(() => {
    let saved: 'dark' | 'light' = 'dark';
    try {
      saved = (localStorage.getItem('opes-theme') as 'dark' | 'light') || 'dark';
    } catch {}
    document.documentElement.setAttribute('data-theme', saved);
    setThemeState(saved);

    const onResize = () => setIsMobile(window.innerWidth < 768);
    onResize();
    window.addEventListener('resize', onResize);
    return () => window.removeEventListener('resize', onResize);
  }, []);

  const showToast = useCallback((msg: string) => {
    if (toastTimer.current) clearTimeout(toastTimer.current);
    setToastMessage(msg);
    setToastVisible(true);
    toastTimer.current = setTimeout(() => setToastVisible(false), 5000);
  }, []);

  const dismissToast = useCallback(() => setToastVisible(false), []);

  const refreshPortfolio = useCallback(async () => {
    try {
      const rows = await api.getPortfolio();
      setPositions(rows);
      setPortfolioError(null);
    } catch (e) {
      setPortfolioError(e instanceof ApiError ? e.message : 'Nie udało się pobrać portfela.');
    } finally {
      setPortfolioLoading(false);
    }
  }, []);

  /* Dane użytkownika ładują się dopiero po zalogowaniu; przy wylogowaniu — czyszczenie. */
  useEffect(() => {
    if (!session) {
      setPositions([]);
      setPortfolioLoading(true);
      setSettingsLoading(true);
      return;
    }
    void refreshPortfolio();
    api
      .getSettings()
      .then(s => {
        setThresholdState(s.relevance_threshold);
        setBaseCurrencyState(s.base_currency ?? 'PLN');
        setSettingsNotif(Boolean((s.notifications as { push?: boolean }).push ?? true));
      })
      .catch(() => {
        /* ustawienia niekrytyczne — zostają wartości domyślne */
      })
      .finally(() => setSettingsLoading(false));
  }, [session, refreshPortfolio]);

  useEffect(() => {
    let cancelled = false;
    const ping = async () => {
      const ok = await api.checkHealth();
      if (!cancelled) setApiOnline(ok);
    };
    void ping();
    const t = setInterval(ping, 30000);
    return () => {
      cancelled = true;
      clearInterval(t);
    };
  }, []);

  const setTheme = useCallback((m: 'dark' | 'light') => {
    try {
      localStorage.setItem('opes-theme', m);
    } catch {}
    document.documentElement.setAttribute('data-theme', m);
    setThemeState(m);
  }, []);

  const addAsset = useCallback(
    async (
      ticker: string,
      type: AssetType,
      qty: number,
      price: number,
      purchasedAt: string,
      currency: string | null,
      physicalForm: PhysicalForm | null = null,
    ) => {
      const t = ticker.trim().toUpperCase();
      if (!t) return false;
      try {
        await api.addPosition({
          ticker: t,
          asset_type: type,
          quantity: qty,
          price,
          currency,
          purchased_at: purchasedAt,
          physical_form: physicalForm,
        });
        // Świeżo dodane aktywo może nie mieć jeszcze snapshotu — dociągnij notowania.
        await api.refreshPrices().catch(() => {});
        await refreshPortfolio();
        showToast(`Zapisano ${t} w portfelu`);
        return true;
      } catch (e) {
        showToast(e instanceof ApiError ? e.message : `Nie udało się dodać ${t}.`);
        return false;
      }
    },
    [refreshPortfolio, showToast],
  );

  const removeAsset = useCallback(
    async (positionId: string) => {
      const pos = positions.find(p => p.id === positionId);
      try {
        await api.removePosition(positionId);
        await refreshPortfolio();
        showToast(pos ? `Usunięto ${pos.asset.ticker} z portfela` : 'Usunięto pozycję');
      } catch (e) {
        showToast(e instanceof ApiError ? e.message : 'Nie udało się usunąć pozycji.');
      }
    },
    [positions, refreshPortfolio, showToast],
  );

  const setSettingsThreshold = useCallback(
    (v: number) => {
      setThresholdState(v);
      if (thresholdSaveTimer.current) clearTimeout(thresholdSaveTimer.current);
      thresholdSaveTimer.current = setTimeout(() => {
        api.updateSettings({ relevance_threshold: v }).catch(() => showToast('Nie udało się zapisać progu trafności.'));
      }, 600);
    },
    [showToast],
  );

  /* Zmiana waluty bazowej: zapis w ustawieniach i ponowne pobranie portfela —
     dashboard przelicza się bez przeładowania strony. */
  const setBaseCurrency = useCallback(
    async (c: BaseCurrency) => {
      const prev = baseCurrency;
      setBaseCurrencyState(c);
      try {
        await api.updateSettings({ base_currency: c });
        await refreshPortfolio();
      } catch {
        setBaseCurrencyState(prev);
        showToast('Nie udało się zapisać waluty bazowej.');
      }
    },
    [baseCurrency, refreshPortfolio, showToast],
  );

  const toggleNotif = useCallback(() => {
    setSettingsNotif(prev => {
      const next = !prev;
      api.updateSettings({ notifications: { push: next } }).catch(() => showToast('Nie udało się zapisać ustawień powiadomień.'));
      return next;
    });
  }, [showToast]);

  return (
    <AppContext.Provider
      value={{
        theme,
        setTheme,
        positions,
        portfolioLoading,
        portfolioError,
        refreshPortfolio,
        addAsset,
        removeAsset,
        settingsThreshold,
        setSettingsThreshold,
        settingsNotif,
        toggleNotif,
        baseCurrency,
        setBaseCurrency,
        settingsLoading,
        apiOnline,
        feedConnectionMode,
        setFeedConnectionMode,
        toastVisible,
        toastMessage,
        showToast,
        dismissToast,
        isMobile,
      }}
    >
      {children}
    </AppContext.Provider>
  );
}

export function useApp(): AppState {
  const ctx = useContext(AppContext);
  if (!ctx) throw new Error('useApp must be used within AppProvider');
  return ctx;
}
