import type { ReactNode } from 'react';
import { Box } from '@mui/material';

/** Contenedor estándar de página a ancho completo dentro del shell. */
export default function PageContainer({ children, maxWidth = 1280 }: { children: ReactNode; maxWidth?: number }) {
  return (
    <Box sx={{ p: { xs: 2, md: 3 }, maxWidth, mx: 'auto', width: '100%' }}>
      {children}
    </Box>
  );
}
