'use client';

import React, { useCallback, useEffect, useRef } from 'react';
import s from './portfolio.module.css';

const FOCUSABLE =
  'a[href],button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex]:not([tabindex="-1"])';

interface DialogProps {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
  labelledBy?: string;
  /** Wariant formularza: nagłówek z przyciskiem zamknięcia i szerszy panel. */
  variant?: 'default' | 'form';
}

export default function Dialog({ title, onClose, children, labelledBy = 'dialog-title', variant = 'default' }: DialogProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const returnFocusRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    returnFocusRef.current = document.activeElement as HTMLElement | null;
    const first = panelRef.current?.querySelector<HTMLElement>(FOCUSABLE);
    first?.focus();
    return () => returnFocusRef.current?.focus();
  }, []);

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        onClose();
        return;
      }
      if (e.key !== 'Tab') return;
      const items = Array.from(panelRef.current?.querySelectorAll<HTMLElement>(FOCUSABLE) ?? []);
      if (items.length === 0) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (e.shiftKey && document.activeElement === first) {
        e.preventDefault();
        last.focus();
      } else if (!e.shiftKey && document.activeElement === last) {
        e.preventDefault();
        first.focus();
      }
    },
    [onClose],
  );

  return (
    <div
      className={s.scrim}
      onMouseDown={e => {
        if (e.target === e.currentTarget) onClose();
      }}
      onKeyDown={onKeyDown}
    >
      <div
        ref={panelRef}
        className={variant === 'form' ? s.dialogForm : s.dialog}
        role="dialog"
        aria-modal="true"
        aria-labelledby={labelledBy}
      >
        {variant === 'form' ? (
          <div className={s.dialogHead}>
            <h2 id={labelledBy} className={s.dialogTitle}>
              {title}
            </h2>
            <button type="button" className={s.iconBtn} aria-label="Zamknij" onClick={onClose}>
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" aria-hidden="true">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
          </div>
        ) : (
          <h2 id={labelledBy} className={s.dialogTitle}>
            {title}
          </h2>
        )}
        {children}
      </div>
    </div>
  );
}
