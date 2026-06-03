import { Box, Card, Typography, LinearProgress, Alert, Table, TableBody, TableCell, TableContainer, TableHead, TableRow } from '@mui/material';
import AccountBalanceWalletOutlined from '@mui/icons-material/AccountBalanceWalletOutlined';
import ReportProblemOutlined from '@mui/icons-material/ReportProblemOutlined';
import CurrencyExchangeOutlined from '@mui/icons-material/CurrencyExchangeOutlined';
import ScheduleOutlined from '@mui/icons-material/ScheduleOutlined';
import { useCarteraDashboard } from '../../hooks/useCxC';
import type { PrioridadCliente } from '../../types/cxc';
import { PageContainer, PageHeader, KpiCard, AgingBars, SectionTitle, StatusChip } from '../../components/ui';
import type { AgingBar } from '../../components/ui';

const BUCKET_LABELS: Record<string, string> = {
  al_dia: 'Al Día',
  '1_30': '1-30 días',
  '31_60': '31-60 días',
  '61_90': '61-90 días',
  mas_90: '+90 días',
};

const BUCKET_GRADIENT: Record<string, string> = {
  al_dia: 'linear-gradient(90deg,#43c463,#4caf50)',
  '1_30': 'linear-gradient(90deg,#ffb547,#ff9800)',
  '31_60': 'linear-gradient(90deg,#ff8a4c,#f57c00)',
  '61_90': 'linear-gradient(90deg,#f2603a,#e64a19)',
  mas_90: 'linear-gradient(90deg,#e0463f,#b71c1c)',
};

const BUCKET_CHIP_COLOR: Record<string, 'success' | 'warning' | 'error'> = {
  al_dia: 'success',
  '1_30': 'warning',
  '31_60': 'warning',
  '61_90': 'error',
  mas_90: 'error',
};

const money = (v: string | number) =>
  `$${parseFloat(String(v)).toLocaleString('es-VE', { minimumFractionDigits: 2 })}`;

export default function DashboardCxCPage() {
  const { data, loading, error } = useCarteraDashboard();

  if (loading) return <Box p={3}><LinearProgress /></Box>;
  if (error) return <Box p={3}><Alert severity="error">{error}</Alert></Box>;
  if (!data) return null;

  const buckets = data.buckets;
  const totalGeneral = parseFloat(data.total_pendiente) || 1;

  const bars: AgingBar[] = Object.entries(buckets).map(([key, val]) => {
    const total = parseFloat(val.total);
    return {
      key,
      label: BUCKET_LABELS[key] ?? key,
      amount: `${money(total)} · ${val.count}`,
      pct: (total / totalGeneral) * 100,
      gradient: BUCKET_GRADIENT[key] ?? 'linear-gradient(90deg,#90a4ae,#607d8b)',
    };
  });

  return (
    <PageContainer>
      <PageHeader title="Dashboard de Cartera" subtitle="Cuentas por cobrar · análisis de antigüedad" />

      {/* KPIs */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' },
          gap: 2,
          mb: 3,
        }}
      >
        <KpiCard label="Total Pendiente" value={money(data.total_pendiente)} icon={<AccountBalanceWalletOutlined />} tone="brand" />
        <KpiCard label="Partidas Vencidas" value={data.partidas_vencidas} icon={<ReportProblemOutlined />} tone="error" emphasizeError />
        <KpiCard
          label="Tasa BCV Hoy"
          value={data.tasa_bcv_hoy ? `Bs. ${parseFloat(data.tasa_bcv_hoy).toLocaleString('es-VE', { minimumFractionDigits: 2 })}` : 'N/D'}
          icon={<CurrencyExchangeOutlined />}
          tone="ai"
        />
        <KpiCard
          label="+90 días"
          value={money(buckets.mas_90.total)}
          icon={<ScheduleOutlined />}
          tone="error"
          emphasizeError
          caption={`${buckets.mas_90.count} facturas`}
        />
      </Box>

      {/* Aging + prioridades */}
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', md: '1fr 1fr' }, gap: 2 }}>
        <Card sx={{ p: 2.5 }}>
          <SectionTitle>Aging por Bucket</SectionTitle>
          <AgingBars bars={bars} />
        </Card>

        <Card sx={{ p: 0, overflow: 'hidden' }}>
          <Box sx={{ p: 2.5, pb: 1.5 }}>
            <SectionTitle>Top Prioridades</SectionTitle>
          </Box>
          <TableContainer>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Cliente</TableCell>
                  <TableCell align="right">Monto</TableCell>
                  <TableCell align="right">Días</TableCell>
                  <TableCell align="center">Estado</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(data.top_prioridades || []).map((p: PrioridadCliente, idx: number) => (
                  <TableRow key={idx}>
                    <TableCell>
                      <Typography variant="body2" noWrap sx={{ maxWidth: 150 }}>{p.cliente_nombre}</Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Typography variant="body2" fontWeight={700} sx={{ fontVariantNumeric: 'tabular-nums' }}>
                        {money(p.monto_pendiente)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">{p.dias_vencida}d</TableCell>
                    <TableCell align="center">
                      <StatusChip
                        value={p.bucket}
                        label={BUCKET_LABELS[p.bucket] || p.bucket}
                        colorMap={BUCKET_CHIP_COLOR}
                      />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Card>
      </Box>
    </PageContainer>
  );
}
