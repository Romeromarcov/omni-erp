import type { ReactNode } from 'react';
import { Box, Paper } from '@mui/material';

interface PageLayoutProps {
  children: ReactNode;
  maxWidth?: number;
}

/**
 * Contenedor centrado tipo "tarjeta" para formularios y vistas de detalle.
 * Se renderiza dentro del shell de la app (no a pantalla completa).
 */
export default function PageLayout({ children, maxWidth = 900 }: PageLayoutProps) {
  return (
    <Box sx={{ p: { xs: 2, md: 3 }, display: 'flex', justifyContent: 'center' }}>
      <Paper variant="outlined" sx={{ width: '100%', maxWidth, p: { xs: 2, md: 4 } }}>
        {children}
      </Paper>
    </Box>
  );
}
