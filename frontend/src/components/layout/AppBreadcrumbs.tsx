import { Breadcrumbs, Link as MuiLink, Typography } from '@mui/material';
import NavigateNextIcon from '@mui/icons-material/NavigateNext';
import HomeOutlined from '@mui/icons-material/HomeOutlined';
import { Link as RouterLink, useLocation } from 'react-router-dom';
import { useMemo } from 'react';
import { buildNavigation } from '../../config/navigation';
import { useAuth } from '../../contexts/AuthContext';

// Map en lugar de Record: `seg` viene de la URL (input del usuario) y un
// objeto plano expondría la cadena de prototipos ("__proto__", "constructor").
const ACTION_LABELS = new Map<string, string>([
  ['new', 'Nuevo'],
  ['crear', 'Nuevo'],
  ['edit', 'Editar'],
]);

function humanize(seg: string): string {
  const accion = ACTION_LABELS.get(seg);
  if (accion) return accion;
  // IDs (uuid / numéricos) → "Detalle"
  if (/^[0-9a-f-]{8,}$/i.test(seg) || /^\d+$/.test(seg)) return 'Detalle';
  return seg.charAt(0).toUpperCase() + seg.slice(1).replace(/-/g, ' ');
}

export default function AppBreadcrumbs() {
  const location = useLocation();
  const { user } = useAuth();
  const empresaId = user?.empresas?.[0]?.id_empresa || '';

  const flat = useMemo(() => {
    const list: { path: string; section: string; item: string }[] = [];
    for (const section of buildNavigation(empresaId)) {
      if (section.path) list.push({ path: section.path, section: section.label, item: '' });
      for (const it of section.items || []) {
        list.push({ path: it.path, section: section.label, item: it.label });
      }
    }
    return list.sort((a, b) => b.path.length - a.path.length);
  }, [empresaId]);

  const pathname = location.pathname;
  if (pathname === '/dashboard') {
    return (
      <Breadcrumbs separator={<NavigateNextIcon fontSize="small" />} sx={{ fontSize: 14 }}>
        <Typography variant="body2" color="text.primary" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          <HomeOutlined fontSize="small" /> Inicio
        </Typography>
      </Breadcrumbs>
    );
  }

  const match = flat.find((e) => pathname === e.path || pathname.startsWith(e.path + '/'));

  const crumbs: { label: string; to?: string }[] = [{ label: 'Inicio', to: '/dashboard' }];
  if (match) {
    if (match.item) {
      crumbs.push({ label: match.section });
      crumbs.push({ label: match.item, to: match.path });
      const rest = pathname.slice(match.path.length).split('/').filter(Boolean);
      if (rest.length) crumbs.push({ label: humanize(rest[rest.length - 1]) });
    } else {
      crumbs.push({ label: match.section, to: match.path });
    }
  } else {
    pathname.split('/').filter(Boolean).forEach((seg) => crumbs.push({ label: humanize(seg) }));
  }

  return (
    <Breadcrumbs separator={<NavigateNextIcon fontSize="small" />} sx={{ fontSize: 14 }}>
      {crumbs.map((c, i) => {
        const last = i === crumbs.length - 1;
        if (last || !c.to) {
          return (
            <Typography key={i} variant="body2" color={last ? 'text.primary' : 'text.secondary'} fontWeight={last ? 600 : 400}>
              {c.label}
            </Typography>
          );
        }
        return (
          <MuiLink
            key={i}
            component={RouterLink}
            to={c.to}
            underline="hover"
            color="text.secondary"
            variant="body2"
            sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}
          >
            {i === 0 && <HomeOutlined fontSize="small" />}
            {c.label}
          </MuiLink>
        );
      })}
    </Breadcrumbs>
  );
}
