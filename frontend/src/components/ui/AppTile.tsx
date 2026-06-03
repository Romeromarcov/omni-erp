import type { ReactNode } from 'react';
import { ButtonBase, Box, Typography } from '@mui/material';

interface AppTileProps {
  label: string;
  icon: ReactNode;
  /** Color de acento (define el fill tintado o el gradiente cuando `gradient`). */
  tint?: string;
  /** Usa gradiente de marca/IA en lugar de fill tintado. */
  gradient?: 'brand' | 'ai';
  onClick?: () => void;
}

/** Tile del lanzador de aplicaciones (estilo Odoo) — icono squircle + etiqueta. */
export default function AppTile({ label, icon, tint = '#1976d2', gradient, onClick }: AppTileProps) {
  const iconStyle =
    gradient === 'ai'
      ? { background: 'var(--omni-ai-gradient)', color: '#fff', boxShadow: 'var(--omni-glow-ai)' }
      : gradient === 'brand'
        ? { background: 'var(--omni-brand-gradient)', color: '#fff', boxShadow: 'var(--omni-glow-primary)' }
        : { background: `${tint}16`, color: tint };

  return (
    <ButtonBase
      onClick={onClick}
      focusRipple
      sx={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 1,
        p: 1,
        borderRadius: 'var(--omni-radius-tile)',
        width: '100%',
        transition: 'transform .12s ease',
        '&:hover': { transform: 'translateY(-2px)' },
      }}
    >
      <Box
        sx={{
          width: 58,
          height: 58,
          borderRadius: '18px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          '& .MuiSvgIcon-root': { fontSize: 26 },
          ...iconStyle,
        }}
      >
        {icon}
      </Box>
      <Typography sx={{ fontSize: 12.5, fontWeight: 600, textAlign: 'center', color: 'text.primary', lineHeight: 1.2 }}>
        {label}
      </Typography>
    </ButtonBase>
  );
}
