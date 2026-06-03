import { Box } from '@mui/material';

interface WordmarkProps {
  /** Tamaño base en px de la parte "Omni". */
  size?: number;
}

/** Logotipo tipográfico: "Omni" en peso 800 + "ERP" espaciado en color de marca. */
export default function Wordmark({ size = 20 }: WordmarkProps) {
  return (
    <Box component="span" sx={{ display: 'inline-flex', alignItems: 'baseline', gap: 0.6, whiteSpace: 'nowrap' }}>
      <Box component="span" sx={{ fontWeight: 800, fontSize: size, letterSpacing: '-0.5px', lineHeight: 1, color: 'text.primary' }}>
        Omni
      </Box>
      <Box component="span" sx={{ fontWeight: 600, fontSize: size * 0.55, letterSpacing: '3px', lineHeight: 1, color: 'primary.main' }}>
        ERP
      </Box>
    </Box>
  );
}
