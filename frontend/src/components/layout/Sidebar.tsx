import { useEffect, useState } from 'react';
import { useLocation, useNavigate } from 'react-router-dom';
import {
  Box,
  Collapse,
  Divider,
  List,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Tooltip,
  Typography,
} from '@mui/material';
import ExpandLess from '@mui/icons-material/ExpandLess';
import ExpandMore from '@mui/icons-material/ExpandMore';
import AutoAwesomeOutlined from '@mui/icons-material/AutoAwesomeOutlined';
import { buildNavigation } from '../../config/navigation';
import type { NavSection } from '../../config/navigation';
import { useAuth } from '../../contexts/AuthContext';
import { useAssistant } from '../../contexts/AssistantContext';
import { BRAND_NAME } from './constants';

interface SidebarProps {
  collapsed: boolean;
  onNavigate?: () => void;
}

function sectionMatchesPath(section: NavSection, pathname: string): boolean {
  if (section.path && pathname.startsWith(section.path)) return true;
  return (section.items || []).some((it) => pathname.startsWith(it.path.split('/_')[0]));
}

export default function Sidebar({ collapsed, onNavigate }: SidebarProps) {
  const navigate = useNavigate();
  const location = useLocation();
  const { user } = useAuth();
  const { setOpen: setAssistantOpen } = useAssistant();
  const empresaId = user?.empresas?.[0]?.id_empresa || '';
  const sections = buildNavigation(empresaId, { esSuperusuarioOmni: user?.es_superusuario_omni ?? false });

  const [openGroups, setOpenGroups] = useState<Record<string, boolean>>({});

  // Auto-abre el grupo correspondiente a la ruta activa.
  useEffect(() => {
    const active = sections.find((s) => s.items && sectionMatchesPath(s, location.pathname));
    if (active) setOpenGroups((prev) => ({ ...prev, [active.id]: true }));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [location.pathname]);

  const go = (path: string) => {
    navigate(path);
    onNavigate?.();
  };

  const isItemActive = (path: string) => location.pathname === path || location.pathname.startsWith(path + '/');

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Brand */}
      <Box
        sx={{
          height: 64,
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          px: collapsed ? 0 : 2,
          justifyContent: collapsed ? 'center' : 'flex-start',
          flexShrink: 0,
        }}
      >
        <Box
          sx={{
            width: 34,
            height: 34,
            borderRadius: 2,
            background: 'linear-gradient(135deg, #1976d2 0%, #42a5f5 100%)',
            color: '#fff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            fontWeight: 800,
            fontSize: 18,
            flexShrink: 0,
          }}
        >
          O
        </Box>
        {!collapsed && (
          <Typography variant="h6" fontWeight={800} noWrap letterSpacing={-0.5}>
            {BRAND_NAME}
          </Typography>
        )}
      </Box>
      <Divider />

      {/* Navigation */}
      <List sx={{ flexGrow: 1, overflowY: 'auto', overflowX: 'hidden', px: 1, py: 1 }}>
        {sections.map((section) => {
          // Sección sin sub-items (Inicio).
          if (!section.items) {
            const active = section.path ? isItemActive(section.path) : false;
            const btn = (
              <ListItemButton
                selected={active}
                onClick={() => section.path && go(section.path)}
                sx={{ borderRadius: 2, mb: 0.5, justifyContent: collapsed ? 'center' : 'flex-start' }}
              >
                <ListItemIcon sx={{ minWidth: collapsed ? 0 : 40, color: active ? 'primary.main' : 'inherit' }}>
                  {section.icon}
                </ListItemIcon>
                {!collapsed && <ListItemText primary={section.label} />}
              </ListItemButton>
            );
            return collapsed ? (
              <Tooltip key={section.id} title={section.label} placement="right">
                {btn}
              </Tooltip>
            ) : (
              <Box key={section.id}>{btn}</Box>
            );
          }

          const groupActive = sectionMatchesPath(section, location.pathname);
          const isOpen = collapsed ? false : openGroups[section.id] ?? false;

          // Modo colapsado: el icono navega al primer item (rail de iconos).
          if (collapsed) {
            return (
              <Tooltip key={section.id} title={section.label} placement="right">
                <ListItemButton
                  selected={groupActive}
                  onClick={() => go(section.items![0].path)}
                  sx={{ borderRadius: 2, mb: 0.5, justifyContent: 'center' }}
                >
                  <ListItemIcon sx={{ minWidth: 0, color: groupActive ? 'primary.main' : 'inherit' }}>
                    {section.icon}
                  </ListItemIcon>
                </ListItemButton>
              </Tooltip>
            );
          }

          return (
            <Box key={section.id}>
              <ListItemButton
                onClick={() => setOpenGroups((prev) => ({ ...prev, [section.id]: !isOpen }))}
                sx={{ borderRadius: 2, mb: 0.5 }}
              >
                <ListItemIcon sx={{ minWidth: 40, color: groupActive ? 'primary.main' : 'inherit' }}>
                  {section.icon}
                </ListItemIcon>
                <ListItemText
                  primary={section.label}
                  primaryTypographyProps={{ fontWeight: groupActive ? 700 : 500 }}
                />
                {isOpen ? <ExpandLess fontSize="small" /> : <ExpandMore fontSize="small" />}
              </ListItemButton>
              <Collapse in={isOpen} timeout="auto" unmountOnExit>
                <List disablePadding>
                  {section.items.map((item) => {
                    const active = isItemActive(item.path);
                    return (
                      <ListItemButton
                        key={item.path}
                        selected={active}
                        onClick={() => go(item.path)}
                        sx={{ borderRadius: 2, mb: 0.25, pl: 5 }}
                      >
                        <ListItemText
                          primary={item.label}
                          primaryTypographyProps={{
                            variant: 'body2',
                            fontWeight: active ? 700 : 400,
                            color: active ? 'primary.main' : 'text.secondary',
                          }}
                        />
                      </ListItemButton>
                    );
                  })}
                </List>
              </Collapse>
            </Box>
          );
        })}
      </List>

      {/* Assistant CTA */}
      <Divider />
      <Box sx={{ p: 1 }}>
        <Tooltip title={collapsed ? 'Asistente IA' : ''} placement="right">
          <ListItemButton
            onClick={() => {
              setAssistantOpen(true);
              onNavigate?.();
            }}
            sx={{
              borderRadius: 2,
              justifyContent: collapsed ? 'center' : 'flex-start',
              bgcolor: 'action.hover',
              '&:hover': { bgcolor: 'action.selected' },
            }}
          >
            <ListItemIcon sx={{ minWidth: collapsed ? 0 : 40, color: 'primary.main' }}>
              <AutoAwesomeOutlined />
            </ListItemIcon>
            {!collapsed && (
              <ListItemText
                primary="Asistente IA"
                primaryTypographyProps={{ fontWeight: 600, color: 'primary.main' }}
              />
            )}
          </ListItemButton>
        </Tooltip>
      </Box>
    </Box>
  );
}
