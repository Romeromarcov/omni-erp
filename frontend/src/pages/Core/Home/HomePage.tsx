import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { Box, Card, Typography } from '@mui/material';
import QrCodeScannerOutlined from '@mui/icons-material/QrCodeScannerOutlined';
import AutoAwesomeOutlined from '@mui/icons-material/AutoAwesomeOutlined';
import ArrowForwardOutlined from '@mui/icons-material/ArrowForwardOutlined';
import { PageContainer, AppTile, BrandMark, SectionTitle } from '../../../components/ui';
import { buildNavigation } from '../../../config/navigation';
import { useAuth } from '../../../contexts/AuthContext';
import { useAssistant } from '../../../contexts/AssistantContext';

/** Acento por dominio para los tiles del lanzador. */
const TINTS: Record<string, string> = {
  dashboard: '#1976d2',
  ventas: '#1976d2',
  escaner: '#7c4dff',
  inventario: '#2e7d32',
  finanzas: '#7c4dff',
  cobranza: '#ed6c02',
  fiscal: '#0288d1',
  empresas: '#546e7a',
  usuarios: '#d32f2f',
  configuracion: '#616161',
  integraciones: '#00897b',
};

/** Página de inicio estilo "app launcher" (Odoo): tiles por dominio + IA + escáner. */
export default function HomePage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { setOpen: setAssistantOpen } = useAssistant();

  const empresa = user?.empresas?.[0];
  const empresaId = empresa?.id_empresa || '';
  const empresaNombre = empresa?.nombre_comercial || empresa?.nombre_legal || empresa?.nombre || 'tu empresa';
  const nombre = user?.first_name || user?.username || 'de nuevo';

  const sections = useMemo(() => buildNavigation(empresaId), [empresaId]);

  const go = (target?: string) => {
    if (target) navigate(target);
  };

  return (
    <PageContainer>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 0.5 }}>
        <BrandMark size={30} />
        <Typography variant="h5">Hola, {nombre} 👋</Typography>
      </Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Tus aplicaciones de Omni ERP · {empresaNombre}
      </Typography>

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: 'repeat(3, 1fr)', sm: 'repeat(5, 1fr)', md: 'repeat(6, 1fr)' },
          gap: { xs: 1.5, sm: 2 },
          mb: 4,
        }}
      >
        <AppTile label="Escáner" icon={<QrCodeScannerOutlined />} gradient="ai" onClick={() => go('/escaner')} />
        {sections
          .filter((s) => s.id !== 'escaner' && s.id !== 'inicio')
          .map((s) => (
            <AppTile
              key={s.id}
              label={s.label}
              icon={s.icon}
              tint={TINTS[s.id] ?? '#1976d2'}
              onClick={() => go(s.path ?? s.items?.[0]?.path)}
            />
          ))}
      </Box>

      <SectionTitle>Asistente IA</SectionTitle>
      <Card
        onClick={() => setAssistantOpen(true)}
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
          p: 2,
          cursor: 'pointer',
          transition: 'box-shadow .15s, transform .12s',
          '&:hover': { transform: 'translateY(-2px)', boxShadow: 'var(--omni-shadow-card-soft)' },
        }}
      >
        <Box
          sx={{
            width: 42,
            height: 42,
            borderRadius: 'var(--omni-radius-tile)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'var(--omni-ai-gradient)',
            color: '#fff',
            boxShadow: 'var(--omni-glow-ai)',
          }}
        >
          <AutoAwesomeOutlined />
        </Box>
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography sx={{ fontWeight: 700, fontSize: 14 }}>Pregúntale a Omni</Typography>
          <Typography sx={{ fontSize: 12.5, color: 'text.secondary' }}>
            Resúmenes, cobranza y más, con el contexto de tu pantalla
          </Typography>
        </Box>
        <ArrowForwardOutlined fontSize="small" sx={{ color: 'primary.main' }} />
      </Card>
    </PageContainer>
  );
}
