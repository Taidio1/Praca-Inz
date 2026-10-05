'use client';

import React, { useEffect, useState } from 'react';
import * as api from '@/lib/api';
import type { SourceFunnel } from '@/lib/types';
import { MONO } from '@/lib/format';

const WINDOWS = [24, 168] as const;

/* Lejek filtra: ile pobrano, ile kandydatów, ile przeszło próg, ile trafiło do LLM. */
export default function FunnelPanel() {
  const [hours, setHours] = useState<(typeof WINDOWS)[number]>(24);
  const [data, setData] = useState<SourceFunnel | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .getSourcesFunnel(hours)
      .then(d => {
        if (!cancelled) {
          setData(d);
          setError(false);
        }
      })
      .catch(() => {
        if (!cancelled) setError(true);
      });
    return () => {
      cancelled = true;
    };
  }, [hours]);

  const steps = data
    ? [
        { label: 'Pobrano', value: data.fetched },
        { label: 'Ocenione', value: data.scored },
        { label: 'Kandydaci', value: data.candidates },
        { label: `Przeszło ≥ ${data.threshold.toFixed(2)}`, value: data.passed },
        { label: 'Do LLM', value: data.sent_to_llm },
        { label: 'Insighty', value: data.insights },
      ]
    : [];
  const max = Math.max(1, ...steps.map(s => s.value));

  return (
    <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--border)' }}>
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 }}>
        <div style={{ fontSize: 10, fontWeight: 700, color: 'var(--muted-2)', textTransform: 'uppercase', letterSpacing: 0.8 }}>
          Lejek filtra trafności
        </div>
        <div style={{ display: 'flex', gap: 4 }}>
          {WINDOWS.map(w => (
            <button
              key={w}
              type="button"
              onClick={() => setHours(w)}
              style={{
                padding: '2px 8px',
                borderRadius: 12,
                border: 'none',
                cursor: 'pointer',
                fontSize: 10.5,
                fontFamily: 'inherit',
                background: hours === w ? 'var(--accent)' : 'var(--panel)',
                color: hours === w ? 'var(--on-accent)' : 'var(--muted)',
              }}
            >
              {w === 24 ? '24 h' : '7 dni'}
            </button>
          ))}
        </div>
      </div>
      {error && <p style={{ fontSize: 12, color: 'var(--neg)' }}>Nie udało się pobrać lejka.</p>}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
        {steps.map(s => (
          <div key={s.label} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <span style={{ width: 120, fontSize: 11, color: 'var(--muted)', flexShrink: 0 }}>{s.label}</span>
            <div style={{ flex: 1, height: 6, background: 'var(--border)', borderRadius: 3, overflow: 'hidden' }}>
              <div style={{ width: `${(s.value / max) * 100}%`, height: '100%', background: 'var(--accent)' }} />
            </div>
            <span style={{ width: 44, textAlign: 'right', fontFamily: MONO, fontSize: 11, color: 'var(--fg-3)' }}>{s.value}</span>
          </div>
        ))}
      </div>
      {data && (
        <div style={{ display: 'flex', gap: 7, marginTop: 8, flexWrap: 'wrap' }}>
          <span style={{ background: 'var(--pos-soft)', border: '1px solid var(--pos-line)', borderRadius: 6, padding: '3px 8px', fontSize: 11, color: 'var(--pos)', fontWeight: 700 }}>
            {data.passed} przeszło
          </span>
          <span style={{ background: 'var(--neg-soft)', border: '1px solid var(--neg-line)', borderRadius: 6, padding: '3px 8px', fontSize: 11, color: 'var(--neg)', fontWeight: 700 }}>
            {data.rejected} odrzucono
          </span>
          <span style={{ borderRadius: 6, padding: '3px 8px', fontSize: 11, color: 'var(--muted)', border: '1px solid var(--border)' }}>
            {data.unmatched} niepasujących
          </span>
          <span style={{ marginLeft: 'auto', fontSize: 10.5, color: 'var(--faint)', fontFamily: MONO }}>
            koszt LLM: {data.cost_usd.toFixed(4)} USD
          </span>
        </div>
      )}
    </div>
  );
}
