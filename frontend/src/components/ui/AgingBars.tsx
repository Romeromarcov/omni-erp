import { Box, Typography } from '@mui/material';

export interface AgingBar {
  key: string;
  label: string;
  /** Texto del monto/recuento a la derecha (ya formateado). */
  amount: string;
  /** Porcentaje de llenado de la barra (0–100). */
  pct: number;
  /** Gradiente o color de relleno de la barra. */
  gradient: string;
}

interface AgingBarsProps {
  bars: AgingBar[];
}

/** Barras de antigüedad de cartera (CxC) con gradiente por bucket. */
export default function AgingBars({ bars }: AgingBarsProps) {
  return (
    <Box>
      {bars.map((b) => (
        <Box key={b.key} sx={{ mb: 1.9, '&:last-of-type': { mb: 0 } }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 1, mb: 0.9 }}>
            <Typography sx={{ fontWeight: 500, fontSize: 13.5 }}>{b.label}</Typography>
            <Typography
              sx={{ fontWeight: 700, fontSize: 12.5, color: 'text.secondary', fontVariantNumeric: 'tabular-nums' }}
            >
              {b.amount}
            </Typography>
          </Box>
          <Box sx={{ height: 9, borderRadius: 999, bgcolor: '#eef1f6', overflow: 'hidden' }}>
            <Box
              sx={{
                height: '100%',
                borderRadius: 999,
                width: `${Math.min(100, Math.max(0, b.pct))}%`,
                background: b.gradient,
                transition: 'width .7s cubic-bezier(.4,0,.2,1)',
              }}
            />
          </Box>
        </Box>
      ))}
    </Box>
  );
}
