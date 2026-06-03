import { useId } from 'react';

interface BrandMarkProps {
  size?: number;
}

/** Isotipo orbital de Omni ERP (anillo + satélite con gradiente de marca). */
export default function BrandMark({ size = 40 }: BrandMarkProps) {
  const gid = useId().replace(/:/g, '');
  return (
    <svg width={size} height={size} viewBox="0 0 56 56" aria-hidden role="img">
      <defs>
        <linearGradient id={gid} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="#1976d2" />
          <stop offset="1" stopColor="#42a5f5" />
        </linearGradient>
      </defs>
      <circle cx="28" cy="28" r="20" fill="none" stroke={`url(#${gid})`} strokeWidth="1.5" opacity="0.35" />
      <circle cx="28" cy="28" r="13" fill="none" stroke={`url(#${gid})`} strokeWidth="4.2" strokeLinecap="round" />
      <circle cx="42" cy="14" r="4.2" fill={`url(#${gid})`} />
    </svg>
  );
}
