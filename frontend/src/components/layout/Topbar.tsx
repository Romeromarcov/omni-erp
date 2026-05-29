import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  AppBar,
  Autocomplete,
  Avatar,
  Box,
  Chip,
  Divider,
  IconButton,
  ListItemIcon,
  Menu,
  MenuItem,
  TextField,
  Toolbar,
  Tooltip,
  Typography,
} from '@mui/material';
import MenuIcon from '@mui/icons-material/Menu';
import SearchOutlined from '@mui/icons-material/SearchOutlined';
import AutoAwesomeOutlined from '@mui/icons-material/AutoAwesomeOutlined';
import BusinessOutlined from '@mui/icons-material/BusinessOutlined';
import AccountCircleOutlined from '@mui/icons-material/AccountCircleOutlined';
import LogoutOutlined from '@mui/icons-material/LogoutOutlined';
import SwitchAccountOutlined from '@mui/icons-material/SwitchAccountOutlined';
import { buildNavigation } from '../../config/navigation';
import { useAuth } from '../../contexts/AuthContext';
import { useAssistant } from '../../contexts/AssistantContext';
import NotificationBell from '../NotificationBell';
import { TOPBAR_HEIGHT } from './constants';

interface TopbarProps {
  onMenuClick: () => void;
  sidebarWidth: number;
  isMobile: boolean;
}

interface SearchOption {
  label: string;
  group: string;
  path: string;
}

export default function Topbar({ onMenuClick, sidebarWidth, isMobile }: TopbarProps) {
  const navigate = useNavigate();
  const { user, logout } = useAuth();
  const { toggle: toggleAssistant } = useAssistant();
  const [anchorEl, setAnchorEl] = useState<null | HTMLElement>(null);

  const empresa = user?.empresas?.[0];
  const empresaId = empresa?.id_empresa || '';
  const empresaNombre = empresa?.nombre_comercial || empresa?.nombre_legal || empresa?.nombre || 'Sin empresa';
  const nombre = `${user?.first_name || ''} ${user?.last_name || ''}`.trim() || user?.username || 'Usuario';
  const iniciales = nombre.split(' ').map((p) => p[0]).slice(0, 2).join('').toUpperCase();

  const searchOptions = useMemo<SearchOption[]>(() => {
    const opts: SearchOption[] = [];
    for (const section of buildNavigation(empresaId)) {
      if (section.path) opts.push({ label: section.label, group: 'General', path: section.path });
      for (const it of section.items || []) {
        opts.push({ label: it.label, group: section.label, path: it.path });
      }
    }
    return opts;
  }, [empresaId]);

  const handleProfile = () => {
    setAnchorEl(null);
    if (empresaId && user?.id) navigate(`/empresas/${empresaId}/usuarios/${user.id}`);
  };
  const handleSwitch = () => {
    setAnchorEl(null);
    logout();
    navigate('/login');
  };
  const handleLogout = () => {
    setAnchorEl(null);
    logout();
    navigate('/login');
  };

  return (
    <AppBar
      position="fixed"
      elevation={0}
      color="inherit"
      sx={{
        width: isMobile ? '100%' : `calc(100% - ${sidebarWidth}px)`,
        ml: isMobile ? 0 : `${sidebarWidth}px`,
        transition: (t) =>
          t.transitions.create(['width', 'margin'], {
            easing: t.transitions.easing.sharp,
            duration: t.transitions.duration.enteringScreen,
          }),
        borderBottom: '1px solid',
        borderColor: 'divider',
        bgcolor: 'background.paper',
      }}
    >
      <Toolbar sx={{ minHeight: `${TOPBAR_HEIGHT}px !important`, gap: 1 }}>
        <IconButton edge="start" onClick={onMenuClick} aria-label="Menú">
          <MenuIcon />
        </IconButton>

        {/* Global search */}
        <Autocomplete
          options={searchOptions}
          groupBy={(o) => o.group}
          getOptionLabel={(o) => o.label}
          onChange={(_, value) => value && navigate(value.path)}
          sx={{ width: { xs: 140, sm: 280, md: 360 } }}
          size="small"
          blurOnSelect
          clearOnBlur
          renderInput={(params) => (
            <TextField
              {...params}
              placeholder="Buscar módulo…"
              variant="outlined"
              InputProps={{
                ...params.InputProps,
                startAdornment: <SearchOutlined fontSize="small" sx={{ color: 'text.secondary', mr: 0.5 }} />,
              }}
            />
          )}
        />

        <Box flexGrow={1} />

        <Chip
          icon={<BusinessOutlined />}
          label={empresaNombre}
          variant="outlined"
          size="small"
          sx={{ display: { xs: 'none', md: 'flex' }, maxWidth: 220 }}
        />

        <Tooltip title="Asistente IA">
          <IconButton color="primary" onClick={toggleAssistant} aria-label="Asistente IA">
            <AutoAwesomeOutlined />
          </IconButton>
        </Tooltip>

        <NotificationBell />

        <Tooltip title={nombre}>
          <IconButton onClick={(e) => setAnchorEl(e.currentTarget)} sx={{ ml: 0.5 }} aria-label="Cuenta">
            <Avatar sx={{ width: 34, height: 34, bgcolor: 'primary.main', fontSize: 14 }}>{iniciales}</Avatar>
          </IconButton>
        </Tooltip>

        <Menu
          anchorEl={anchorEl}
          open={Boolean(anchorEl)}
          onClose={() => setAnchorEl(null)}
          transformOrigin={{ horizontal: 'right', vertical: 'top' }}
          anchorOrigin={{ horizontal: 'right', vertical: 'bottom' }}
          slotProps={{ paper: { sx: { mt: 1, minWidth: 220 } } }}
        >
          <Box sx={{ px: 2, py: 1 }}>
            <Typography variant="subtitle2" noWrap>{nombre}</Typography>
            <Typography variant="caption" color="text.secondary" noWrap>{user?.email}</Typography>
          </Box>
          <Divider />
          <MenuItem onClick={handleProfile}>
            <ListItemIcon><AccountCircleOutlined fontSize="small" /></ListItemIcon>
            Mi perfil
          </MenuItem>
          <MenuItem onClick={handleSwitch}>
            <ListItemIcon><SwitchAccountOutlined fontSize="small" /></ListItemIcon>
            Cambiar empresa/sucursal
          </MenuItem>
          <Divider />
          <MenuItem onClick={handleLogout} sx={{ color: 'error.main' }}>
            <ListItemIcon><LogoutOutlined fontSize="small" color="error" /></ListItemIcon>
            Cerrar sesión
          </MenuItem>
        </Menu>
      </Toolbar>
    </AppBar>
  );
}
