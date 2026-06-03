import type { ReactNode } from 'react';
import { Box, Card, Typography } from '@mui/material';

export type KpiTone = 'brand' | 'ai' | 'tint' | 'error' | 'success' | 'warning';

interface KpiCardProps {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  /** Estilo del tile del icono. */
  tone?: KpiTone;
  caption?: ReactNode;
  /** Resalta el valor en color de error. */
  emphasizeError?: boolean;
}

const TILE_STYLE: Record<KpiTone, object> = {
  brand: {
    background: 'var(--omni-brand-gradient)',
    color: '#fff',
    boxShadow: 'var(--omni-glow-primary)',
  },
  ai: {
    background: 'var(--omni-ai-gradient)',
    color: '#fff',
    boxShadow: 'var(--omni-glow-ai)',
  },
  tint: { background: 'var(--omni-tint-primary)', color: 'primary.main' },
  error: { background: 'var(--omni-tint-error)', color: 'error.main' },
  success: { background: 'var(--omni-tint-success)', color: 'success.main' },
  warning: { background: 'var(--omni-tint-warning)', color: 'warning.dark' },
};

/** Tarjeta KPI futurista: etiqueta + valor grande + tile de icono con gradiente/tinte. */
export default function KpiCard({ label, value, icon, tone = 'brand', caption, emphasizeError }: KpiCardProps) {
  return (
    <Card sx={{ p: 2, height: '100%' }}>
      <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', mb: 1.25, gap: 1 }}>
        <Typography
          sx={{
            fontWeight: 700,
            fontSize: 10,
            lineHeight: 1.3,
            letterSpacing: '0.04em',
            textTransform: 'uppercase',
            color: 'text.secondary',
          }}
        >
          {label}
        </Typography>
        {icon && (
          <Box
            sx={{
              width: 34,
              height: 34,
              flexShrink: 0,
              borderRadius: 'var(--omni-radius-tile)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              '& .MuiSvgIcon-root': { fontSize: 18 },
              ...TILE_STYLE[tone],
            }}
          >
            {icon}
          </Box>
        )}
      </Box>
      <Typography
        sx={{
          fontWeight: 800,
          fontSize: 24,
          lineHeight: 1.05,
          letterSpacing: '-0.5px',
          fontVariantNumeric: 'tabular-nums',
          color: emphasizeError ? 'error.main' : 'text.primary',
        }}
      >
        {value}
      </Typography>
      {caption && (
        <Typography sx={{ fontWeight: 500, fontSize: 11.5, color: 'text.secondary', mt: 0.5 }}>{caption}</Typography>
      )}
    </Card>
  );
}
