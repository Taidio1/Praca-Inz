'use client';

import { useEffect, useRef, useState } from 'react';

/* Szerokość kontenera dla wykresów SVG rysowanych w pikselach (bez rozciągania tekstu). */
export function useWidth<T extends HTMLElement>() {
  const ref = useRef<T>(null);
  const [width, setWidth] = useState(0);
  useEffect(() => {
    if (!ref.current) return;
    const ro = new ResizeObserver(entries => setWidth(entries[0].contentRect.width));
    ro.observe(ref.current);
    return () => ro.disconnect();
  }, []);
  return [ref, width] as const;
}
