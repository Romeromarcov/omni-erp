import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CircularProgress from '@mui/material/CircularProgress';
import Grid from '@mui/material/Grid';
import LinearProgress from '@mui/material/LinearProgress';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import ToggleButton from '@mui/material/ToggleButton';
import ToggleButtonGroup from '@mui/material/ToggleButtonGroup';
import Typography from '@mui/material/Typography';
import CheckCircleOutlined from '@mui/icons-material/CheckCircleOutlined';
import GroupOutlined from '@mui/icons-material/GroupOutlined';
import PersonAddAltOutlined from '@mui/icons-material/PersonAddAltOutlined';
import RefreshOutlined from '@mui/icons-material/RefreshOutlined';
import TouchAppOutlined from '@mui/icons-material/TouchAppOutlined';
import TrendingUpOutlined from '@mui/icons-material/TrendingUpOutlined';
import {
  DataTable,
  KpiCard,
  PageContainer,
  PageHeader,
  SectionTitle,
  type Column,
} from '../../components/ui';
import { connectKeys } from '../../lib/queryKeys';
import {
  getAnaliticasConnect,
  getPerfilesConnect,
  type ConnectAnaliticasResponse,
  type ConnectAnaliticasSerieDia,
  type ConnectAnaliticasTopPerfil,
  type ConnectPerfil,
} from '../../services/connectService';
import { mensajeDeError } from '../../utils/api';
import { getEmpresaId } from '../../utils/empresa';

type PeriodoDias = 7 | 30 | 90;

const PERIODOS: readonly PeriodoDias[] = [7, 30, 90];

const ORIGEN_LABELS = new Map<string, string>([
  ['NFC', 'Tarjeta NFC'],
  ['QR', 'Código QR'],
  ['ENLACE', 'Enlace directo'],
]);

const DISPOSITIVO_LABELS = new Map<string, string>([
  ['IOS', 'iOS'],
  ['ANDROID', 'Android'],
  ['ESCRITORIO', 'Escritorio'],
  ['OTRO', 'Otro'],
]);

function calcularPorcentaje(valor: number, total: number): number {
  if (total <= 0 || valor <= 0) return 0;
  return Math.min(100, Math.round((valor / total) * 100));
}

function BreakdownCard({
  title,
  entries,
  labels,
  emptyMessage,
}: {
  title: string;
  entries: Array<[string, number]>;
  labels: Map<string, string>;
  emptyMessage: string;
}) {
  const total = entries.reduce((acc, [, count]) => acc + count, 0);

  return (
    <Card sx={{ height: '100%' }}>
      <CardContent>
        <SectionTitle>{title}</SectionTitle>
        {entries.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            {emptyMessage}
          </Typography>
        ) : (
          <Stack spacing={1.75}>
            {entries.map(([clave, conteo]) => {
              const porcentaje = calcularPorcentaje(conteo, total);
              const etiqueta = labels.get(clave) ?? clave;
              return (
                <Box key={clave}>
                  <Stack direction="row" justifyContent="space-between" alignItems="baseline" mb={0.5}>
                    <Typography variant="body2" fontWeight={600}>
                      {etiqueta}
                    </Typography>
                    <Typography variant="body2" color="text.secondary" sx={{ fontVariantNumeric: 'tabular-nums' }}>
                      {conteo} ({porcentaje}%)
                    </Typography>
                  </Stack>
                  <LinearProgress
                    variant="determinate"
                    value={porcentaje}
                    sx={{ height: 7, borderRadius: 4 }}
                  />
                </Box>
              );
            })}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
}

export default function ConnectAnaliticasPage() {
  const empresaId = getEmpresaId();
  const [dias, setDias] = useState<PeriodoDias>(30);
  const [perfilId, setPerfilId] = useState<string>('');

  const perfilesQuery = useQuery<ConnectPerfil[]>({
    queryKey: connectKeys.perfiles(empresaId),
    queryFn: () => getPerfilesConnect(empresaId),
  });

  const analiticasQuery = useQuery<ConnectAnaliticasResponse>({
    queryKey: connectKeys.analiticas(empresaId, {
      dias,
      perfilId: perfilId || null,
    }),
    queryFn: () =>
      getAnaliticasConnect({
        empresaId,
        dias,
        perfilId: perfilId || null,
      }),
  });

  const perfiles = perfilesQuery.data ?? [];
  const data = analiticasQuery.data;

  const topPerfilesColumns: Column<ConnectAnaliticasTopPerfil>[] = [
    {
      key: 'perfil',
      header: 'Perfil',
      render: (row) => (
        <Box>
          <Typography variant="body2" fontWeight={600}>
            {row.nombre_publico}
          </Typography>
          <Typography variant="caption" color="text.secondary" fontFamily="monospace">
            /c/{row.slug}
          </Typography>
        </Box>
      ),
    },
    {
      key: 'toques',
      header: 'Toques',
      align: 'right',
      render: (row) => row.toques,
    },
    {
      key: 'visitantes_unicos',
      header: 'Visitantes únicos',
      align: 'right',
      render: (row) => row.visitantes_unicos,
    },
    {
      key: 'leads',
      header: 'Leads',
      align: 'right',
      render: (row) => row.leads,
    },
    {
      key: 'leads_convertidos',
      header: 'Convertidos',
      align: 'right',
      render: (row) => row.leads_convertidos,
    },
    {
      key: 'tasa_conversion_pct',
      header: 'Conversión',
      align: 'right',
      render: (row) => `${row.tasa_conversion_pct}%`,
    },
  ];

  const maxToquesDia = Math.max(1, ...(data?.serie_diaria.map((d) => d.toques) ?? [1]));

  const serieDiariaColumns: Column<ConnectAnaliticasSerieDia>[] = [
    {
      key: 'fecha',
      header: 'Fecha',
      render: (row) => (
        <Typography variant="body2" fontFamily="monospace">
          {row.fecha}
        </Typography>
      ),
    },
    {
      key: 'toques',
      header: 'Toques',
      align: 'right',
      render: (row) => row.toques,
    },
    {
      key: 'leads',
      header: 'Leads',
      align: 'right',
      render: (row) => row.leads,
    },
    {
      key: 'actividad',
      header: 'Actividad diaria',
      width: '35%',
      render: (row) => (
        <LinearProgress
          variant="determinate"
          value={calcularPorcentaje(row.toques, maxToquesDia)}
          sx={{ height: 6, borderRadius: 3 }}
        />
      ),
    },
  ];

  const headerActions = (
    <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.25} alignItems={{ xs: 'stretch', sm: 'center' }}>
      <ToggleButtonGroup
        size="small"
        exclusive
        value={dias}
        aria-label="Periodo de analíticas"
        onChange={(_, next: PeriodoDias | null) => {
          if (next !== null) setDias(next);
        }}
      >
        {PERIODOS.map((p) => (
          <ToggleButton key={p} value={p}>
            {p} días
          </ToggleButton>
        ))}
      </ToggleButtonGroup>

      <TextField
        select
        size="small"
        label="Perfil"
        value={perfilId}
        onChange={(e) => setPerfilId(e.target.value)}
        sx={{ minWidth: 200 }}
      >
        <MenuItem value="">Todos los perfiles</MenuItem>
        {perfiles.map((p) => (
          <MenuItem key={p.id_perfil} value={p.id_perfil}>
            {p.nombre_publico} (/c/{p.slug})
          </MenuItem>
        ))}
      </TextField>
    </Stack>
  );

  return (
    <PageContainer>
      <PageHeader
        title="Analíticas Omni Connect"
        subtitle="Seguimiento de toques NFC/QR, visitantes únicos y conversión de leads por periodo."
        actions={headerActions}
      />

      {analiticasQuery.isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress aria-label="Cargando analíticas" />
        </Box>
      ) : analiticasQuery.isError ? (
        <Alert
          severity="error"
          action={
            <Button
              color="inherit"
              size="small"
              startIcon={<RefreshOutlined />}
              onClick={() => void analiticasQuery.refetch()}
            >
              Reintentar
            </Button>
          }
        >
          {mensajeDeError(analiticasQuery.error, 'No se pudieron cargar las analíticas de Omni Connect.')}
        </Alert>
      ) : data ? (
        <Stack spacing={3}>
          <Typography variant="body2" color="text.secondary">
            Periodo consultado: {data.periodo.desde} al {data.periodo.hasta} ({data.periodo.dias} días)
          </Typography>

          <Grid container spacing={2}>
            <Grid size={{ xs: 12, sm: 6, md: 4, lg: 2.4 }}>
              <KpiCard
                label="Total toques"
                value={data.total_toques}
                icon={<TouchAppOutlined />}
                tone="brand"
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 4, lg: 2.4 }}>
              <KpiCard
                label="Visitantes únicos"
                value={data.visitantes_unicos}
                icon={<GroupOutlined />}
                tone="tint"
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 4, lg: 2.4 }}>
              <KpiCard
                label="Total leads"
                value={data.total_leads}
                icon={<PersonAddAltOutlined />}
                tone="ai"
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 6, md: 6, lg: 2.4 }}>
              <KpiCard
                label="Leads convertidos"
                value={data.leads_convertidos}
                icon={<CheckCircleOutlined />}
                tone="success"
                caption={`Tasa de cierre: ${data.tasa_cierre_pct}%`}
              />
            </Grid>
            <Grid size={{ xs: 12, sm: 12, md: 6, lg: 2.4 }}>
              <KpiCard
                label="Tasa de conversión"
                value={`${data.tasa_conversion_pct}%`}
                icon={<TrendingUpOutlined />}
                tone="warning"
                caption="Leads / toques"
              />
            </Grid>
          </Grid>

          <Grid container spacing={2.5}>
            <Grid size={{ xs: 12, md: 6 }}>
              <BreakdownCard
                title="Desglose por origen"
                entries={Object.entries(data.por_origen)}
                labels={ORIGEN_LABELS}
                emptyMessage="Sin datos de origen en este periodo."
              />
            </Grid>
            <Grid size={{ xs: 12, md: 6 }}>
              <BreakdownCard
                title="Desglose por dispositivo"
                entries={Object.entries(data.por_dispositivo)}
                labels={DISPOSITIVO_LABELS}
                emptyMessage="Sin datos de dispositivos en este periodo."
              />
            </Grid>
          </Grid>

          <Box>
            <SectionTitle>Top perfiles</SectionTitle>
            <DataTable
              columns={topPerfilesColumns}
              rows={data.top_perfiles}
              getRowKey={(row) => row.id_perfil}
              emptyMessage="Sin actividad de perfiles en el periodo seleccionado."
            />
          </Box>

          <Box>
            <SectionTitle>Serie diaria</SectionTitle>
            <DataTable
              columns={serieDiariaColumns}
              rows={data.serie_diaria}
              getRowKey={(row) => row.fecha}
              emptyMessage="No hay registros diarios en el periodo seleccionado."
            />
          </Box>
        </Stack>
      ) : null}
    </PageContainer>
  );
}
