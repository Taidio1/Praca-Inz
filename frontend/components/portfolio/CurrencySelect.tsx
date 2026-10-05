'use client';

import React, { useEffect, useId, useRef, useState } from 'react';
import { CURRENCIES, currencyInfo } from '@/lib/currency';
import s from './portfolio.module.css';

/* Wybór waluty transakcji: symbol, pełna nazwa i kod. ✕ wraca do waluty notowania. */
export default function CurrencySelect({
  value,
  quoteCurrency,
  onChange,
  disabled,
}: {
  value: string | null;
  quoteCurrency: string | null;
  onChange: (code: string | null) => void;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [highlighted, setHighlighted] = useState(0);
  const rootRef = useRef<HTMLDivElement>(null);
  const listId = useId();

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const openList = () => {
    if (disabled) return;
    const idx = CURRENCIES.findIndex(c => c.code === value);
    setHighlighted(idx >= 0 ? idx : 0);
    setOpen(true);
  };

  const pick = (code: string) => {
    onChange(code === quoteCurrency ? null : code);
    setOpen(false);
  };

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (!open) {
      if (e.key === 'Enter' || e.key === ' ' || e.key === 'ArrowDown') {
        e.preventDefault();
        openList();
      }
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      e.stopPropagation(); // nie zamykaj całego okna
      setOpen(false);
    } else if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlighted(i => Math.min(CURRENCIES.length - 1, i + 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlighted(i => Math.max(0, i - 1));
    } else if (e.key === 'Enter' || e.key === ' ') {
      e.preventDefault();
      pick(CURRENCIES[highlighted].code);
    }
  };

  const info = value ? currencyInfo(value) : null;
  const differs = value != null && quoteCurrency != null && value !== quoteCurrency;

  return (
    <div ref={rootRef} className={s.currencyField}>
      <button
        type="button"
        className={s.currencyPicker}
        aria-haspopup="listbox"
        aria-expanded={open}
        aria-controls={listId}
        disabled={disabled}
        onClick={() => (open ? setOpen(false) : openList())}
        onKeyDown={onKeyDown}
      >
        <span className={s.currency}>
          <span className={s.currencyIcon} aria-hidden="true">
            {info?.symbol ?? '¤'}
          </span>
          <span style={{ minWidth: 0 }}>
            <span className={s.instrumentName} style={{ display: 'block' }}>
              {info?.name ?? 'Ustawi się po wyborze instrumentu'}
            </span>
            <span className={s.instrumentMeta} style={{ display: 'block' }}>
              {info ? info.code : '—'}
              {info && !differs && quoteCurrency ? ' · waluta notowania' : ''}
              {differs ? ` · notowanie w ${quoteCurrency}` : ''}
            </span>
          </span>
        </span>
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" className={s.currencyChevron}>
          <path d="M6 9l6 6 6-6" />
        </svg>
      </button>
      {differs && (
        <button
          type="button"
          className={s.iconBtn}
          aria-label={`Przywróć walutę notowania (${quoteCurrency})`}
          title={`Przywróć walutę notowania (${quoteCurrency})`}
          onClick={() => onChange(null)}
        >
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        </button>
      )}
      {open && (
        <ul id={listId} role="listbox" aria-label="Waluta" className={s.currencyMenu}>
          {CURRENCIES.map((c, i) => (
            <li
              key={c.code}
              role="option"
              aria-selected={c.code === value}
              className={[
                s.currencyOption,
                i === highlighted ? s.currencyOptionActive : '',
                c.code === value ? s.currencyOptionSelected : '',
              ]
                .filter(Boolean)
                .join(' ')}
              onMouseDown={e => {
                e.preventDefault();
                pick(c.code);
              }}
              onMouseEnter={() => setHighlighted(i)}
            >
              <span className={s.currencyOptionSymbol} aria-hidden="true">
                {c.symbol}
              </span>
              <span className={s.currencyOptionName}>{c.name}</span>
              <span className={`${s.currencyOptionCode} mono`}>{c.code}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
