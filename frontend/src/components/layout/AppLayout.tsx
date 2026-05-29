import { Suspense, useState } from 'react';
import { Outlet } from 'react-router-dom';
import { Box, CircularProgress, Drawer, Toolbar, useMediaQuery, useTheme } from '@mui/material';
import { AssistantProvider } from '../../contexts/AssistantContext';
import AssistantDrawer from '../assistant/AssistantDrawer';
import Topbar from './Topbar';
import Sidebar from './Sidebar';
import AppBreadcrumbs from './AppBreadcrumbs';
import { DRAWER_WIDTH, RAIL_WIDTH, TOPBAR_HEIGHT } from './constants';

function PageLoader() {
  return (
    <Box display="flex" justifyContent="center" alignItems="center" minHeight="50vh">
      <CircularProgress />
    </Box>
  );
}

export default function AppLayout() {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const [collapsed, setCollapsed] = useState(localStorage.getItem('sidebar_collapsed') === '1');
  const [mobileOpen, setMobileOpen] = useState(false);

  const sidebarWidth = collapsed ? RAIL_WIDTH : DRAWER_WIDTH;

  const handleMenuClick = () => {
    if (isMobile) {
      setMobileOpen((o) => !o);
    } else {
      setCollapsed((c) => {
        localStorage.setItem('sidebar_collapsed', c ? '0' : '1');
        return !c;
      });
    }
  };

  return (
    <AssistantProvider>
      <Box sx={{ display: 'flex', minHeight: '100vh', bgcolor: 'background.default' }}>
        <Topbar onMenuClick={handleMenuClick} sidebarWidth={sidebarWidth} isMobile={isMobile} />

        {/* Sidebar permanente (desktop) */}
        <Drawer
          variant="permanent"
          sx={{
            display: { xs: 'none', md: 'block' },
            width: sidebarWidth,
            flexShrink: 0,
            '& .MuiDrawer-paper': {
              width: sidebarWidth,
              boxSizing: 'border-box',
              borderRight: '1px solid',
              borderColor: 'divider',
              overflowX: 'hidden',
              transition: theme.transitions.create('width', {
                easing: theme.transitions.easing.sharp,
                duration: theme.transitions.duration.enteringScreen,
              }),
            },
          }}
          open
        >
          <Sidebar collapsed={collapsed} />
        </Drawer>

        {/* Sidebar temporal (mobile) */}
        <Drawer
          variant="temporary"
          open={mobileOpen}
          onClose={() => setMobileOpen(false)}
          ModalProps={{ keepMounted: true }}
          sx={{
            display: { xs: 'block', md: 'none' },
            '& .MuiDrawer-paper': { width: DRAWER_WIDTH, boxSizing: 'border-box' },
          }}
        >
          <Sidebar collapsed={false} onNavigate={() => setMobileOpen(false)} />
        </Drawer>

        {/* Contenido principal */}
        <Box component="main" sx={{ flexGrow: 1, minWidth: 0, display: 'flex', flexDirection: 'column' }}>
          <Toolbar sx={{ minHeight: `${TOPBAR_HEIGHT}px !important` }} />
          <Box
            sx={{
              px: { xs: 2, md: 3 },
              py: 1.25,
              borderBottom: '1px solid',
              borderColor: 'divider',
              bgcolor: 'background.paper',
            }}
          >
            <AppBreadcrumbs />
          </Box>
          <Box sx={{ flexGrow: 1 }}>
            <Suspense fallback={<PageLoader />}>
              <Outlet />
            </Suspense>
          </Box>
        </Box>

        <AssistantDrawer />
      </Box>
    </AssistantProvider>
  );
}
