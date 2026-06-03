import { createTheme } from '@mui/material/styles';

/**
 * Theme de Omni ERP — dirección de diseño futurista sobre Material (MUI v7).
 * Squircles, fills tintados, hairline y sombras suaves con glow. Los overrides
 * de componentes propagan la identidad a todas las páginas sin tocarlas una a una.
 */
const FONT_FAMILY = '"Inter", "Roboto", "Helvetica", "Arial", sans-serif';

const SHADOW_CARD_SOFT = '0 4px 20px rgba(16,42,80,0.06)';
const HAIRLINE = '1px solid rgba(16,42,80,0.08)';

export const theme = createTheme({
  palette: {
    primary: { main: '#1976d2', light: '#42a5f5', dark: '#1565c0', contrastText: '#fff' },
    secondary: { main: '#dc004e', light: '#e33371', dark: '#9a0036' },
    success: { main: '#2e7d32', light: '#4caf50', dark: '#1b5e20' },
    warning: { main: '#ed6c02', light: '#ff9800', dark: '#e65100' },
    error: { main: '#d32f2f', light: '#ef5350', dark: '#c62828' },
    info: { main: '#0288d1', light: '#03a9f4', dark: '#01579b' },
    background: { default: '#f4f6f8', paper: '#ffffff' },
    divider: 'rgba(16,42,80,0.08)',
  },
  typography: {
    fontFamily: FONT_FAMILY,
    h4: { fontWeight: 700, letterSpacing: '-0.5px' },
    h5: { fontWeight: 700, letterSpacing: '-0.3px' },
    h6: { fontWeight: 600 },
    subtitle1: { fontWeight: 600 },
    subtitle2: { fontWeight: 600 },
    button: { fontWeight: 600 },
  },
  shape: { borderRadius: 8 },
  components: {
    MuiButton: {
      defaultProps: { disableElevation: true },
      styleOverrides: {
        root: { textTransform: 'none', fontWeight: 600, borderRadius: 10 },
        containedPrimary: {
          background: 'linear-gradient(135deg,#1976d2 0%,#42a5f5 100%)',
          boxShadow: '0 8px 20px rgba(25,118,210,0.30)',
          '&:hover': { background: 'linear-gradient(135deg,#1565c0 0%,#1976d2 100%)' },
          '&.Mui-disabled': { background: 'rgba(0,0,0,0.12)', boxShadow: 'none' },
        },
      },
    },
    MuiCard: {
      styleOverrides: {
        root: {
          borderRadius: 16,
          border: HAIRLINE,
          boxShadow: SHADOW_CARD_SOFT,
          backgroundImage: 'none',
        },
      },
    },
    MuiPaper: {
      styleOverrides: {
        rounded: { borderRadius: 14 },
      },
    },
    MuiOutlinedInput: {
      styleOverrides: {
        root: { borderRadius: 12 },
      },
    },
    MuiTableHead: {
      styleOverrides: {
        root: {
          '& .MuiTableCell-root': {
            fontWeight: 700,
            color: 'rgba(0,0,0,0.6)',
            backgroundColor: '#f4f6f8',
            borderBottom: '1px solid rgba(16,42,80,0.10)',
          },
        },
      },
    },
    MuiTableCell: {
      styleOverrides: {
        root: { borderColor: 'rgba(16,42,80,0.06)' },
      },
    },
    MuiChip: {
      styleOverrides: {
        root: { fontWeight: 600 },
      },
    },
    MuiToggleButton: {
      styleOverrides: {
        root: { textTransform: 'none', fontWeight: 600 },
      },
    },
    MuiListItemButton: {
      styleOverrides: {
        root: {
          borderRadius: 10,
          '&.Mui-selected': { backgroundColor: 'rgba(25,118,210,0.08)' },
          '&.Mui-selected:hover': { backgroundColor: 'rgba(25,118,210,0.12)' },
        },
      },
    },
    MuiTooltip: {
      styleOverrides: {
        tooltip: { borderRadius: 8, fontSize: 12, fontWeight: 500 },
      },
    },
  },
});

export default theme;
