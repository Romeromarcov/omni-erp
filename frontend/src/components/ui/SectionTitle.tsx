import type { ReactNode } from 'react';
import { Box, Typography } from '@mui/material';

interface SectionTitleProps {
  children: ReactNode;
  action?: ReactNode;
}

/** Título de sección compacto con acción opcional a la derecha. */
export default function SectionTitle({ children, action }: SectionTitleProps) {
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 1, mb: 1.5 }}>
      <Typography sx={{ fontWeight: 700, fontSize: 15, letterSpacing: '-0.2px' }}>{children}</Typography>
      {action}
    </Box>
  );
}
