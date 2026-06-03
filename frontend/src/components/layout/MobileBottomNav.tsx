import { BottomNavigation, BottomNavigationAction, Paper } from '@mui/material';
import { useLocation, useNavigate } from 'react-router-dom';
import SpaceDashboardOutlined from '@mui/icons-material/SpaceDashboardOutlined';
import PointOfSaleOutlined from '@mui/icons-material/PointOfSaleOutlined';
import RequestQuoteOutlined from '@mui/icons-material/RequestQuoteOutlined';
import AutoAwesomeOutlined from '@mui/icons-material/AutoAwesomeOutlined';
import MenuOutlined from '@mui/icons-material/MenuOutlined';
import { useAssistant } from '../../contexts/AssistantContext';
import { MOBILE_NAV_HEIGHT } from './constants';

interface MobileBottomNavProps {
  /** Abre el cajón de navegación completo (pestaña "Más"). */
  onMore: () => void;
}

const TABS = [
  { value: 'inicio', label: 'Inicio', icon: <SpaceDashboardOutlined />, path: '/dashboard' },
  { value: 'ventas', label: 'Ventas', icon: <PointOfSaleOutlined />, path: '/ventas/pedidos' },
  { value: 'cobranza', label: 'CxC', icon: <RequestQuoteOutlined />, path: '/cobranza/dashboard' },
  { value: 'ia', label: 'IA', icon: <AutoAwesomeOutlined />, path: null },
  { value: 'mas', label: 'Más', icon: <MenuOutlined />, path: null },
] as const;

function resolveActive(pathname: string): string {
  if (pathname.startsWith('/ventas')) return 'ventas';
  if (pathname.startsWith('/cobranza')) return 'cobranza';
  if (pathname.startsWith('/dashboard')) return 'inicio';
  return '';
}

/**
 * Barra de pestañas inferior para móvil (Inicio · Ventas · CxC · IA · Más).
 * Solo visible por debajo del breakpoint `md`; complementa el cajón lateral.
 */
export default function MobileBottomNav({ onMore }: MobileBottomNavProps) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const { toggle: toggleAssistant } = useAssistant();
  const active = resolveActive(pathname);

  return (
    <Paper
      elevation={8}
      sx={{
        display: { xs: 'block', md: 'none' },
        position: 'fixed',
        bottom: 0,
        left: 0,
        right: 0,
        zIndex: (t) => t.zIndex.appBar,
        borderTop: '1px solid',
        borderColor: 'divider',
        pb: 'env(safe-area-inset-bottom)',
      }}
    >
      <BottomNavigation
        value={active}
        showLabels
        sx={{ height: MOBILE_NAV_HEIGHT }}
        onChange={(_, value) => {
          if (value === 'mas') return onMore();
          if (value === 'ia') return toggleAssistant();
          const tab = TABS.find((t) => t.value === value);
          if (tab?.path) navigate(tab.path);
        }}
      >
        {TABS.map((t) => (
          <BottomNavigationAction key={t.value} value={t.value} label={t.label} icon={t.icon} />
        ))}
      </BottomNavigation>
    </Paper>
  );
}
