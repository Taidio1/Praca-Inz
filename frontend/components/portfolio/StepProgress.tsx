'use client';

import React from 'react';
import s from './portfolio.module.css';

/**
 * Pasek postępu kroków dialogu: każdy krok zajmuje równą część szerokości i ma własny
 * odcinek paska. Ukończone kroki można kliknąć, żeby do nich wrócić.
 */
export default function StepProgress({
  steps,
  current,
  onStepClick,
}: {
  steps: string[];
  current: number;
  onStepClick?: (index: number) => void;
}) {
  return (
    <ol className={s.stepper} aria-label="Postęp dodawania aktywa">
      {steps.map((label, i) => {
        const state = i < current ? 'done' : i === current ? 'active' : 'todo';
        const content = (
          <>
            <span className={s.stepperHead}>
              <span className={s.stepperDot} data-state={state}>
                {state === 'done' ? (
                  <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                    <path d="M5 12.5l4.5 4.5L19 7.5" />
                  </svg>
                ) : (
                  i + 1
                )}
              </span>
              <span className={s.stepperLabel} data-state={state}>
                {label}
              </span>
            </span>
            <span className={s.stepperTrack}>
              <span className={s.stepperFill} data-state={state} />
            </span>
          </>
        );
        return (
          <li key={label} className={s.stepperItem} aria-current={state === 'active' ? 'step' : undefined}>
            {state === 'done' && onStepClick ? (
              <button type="button" className={s.stepperBtn} onClick={() => onStepClick(i)} title={`Wróć do kroku: ${label}`}>
                {content}
              </button>
            ) : (
              <span className={s.stepperBtn}>{content}</span>
            )}
          </li>
        );
      })}
    </ol>
  );
}
