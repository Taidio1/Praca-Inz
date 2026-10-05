import React from 'react';
import { fmtFxDate, fxSourceLabel } from '@/lib/currency';
import s from './portfolio.module.css';

/* Mała adnotacja przy sumach: z jakiego dnia i źródła pochodzi kurs przeliczenia. */
export default function FxNote({
  date,
  sources,
  style,
}: {
  date: string | null | undefined;
  sources: string[];
  style?: React.CSSProperties;
}) {
  if (!date) return null;
  const labels = sources.map(fxSourceLabel).filter((l): l is string => Boolean(l));
  return (
    <span className={s.fxAnnotation} style={style}>
      Przeliczono po kursie z {fmtFxDate(date)}
      {labels.length > 0 ? `, źródło: ${labels.join(', ')}` : ''}
    </span>
  );
}
