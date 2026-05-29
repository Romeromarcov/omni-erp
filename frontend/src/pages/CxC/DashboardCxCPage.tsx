import { Box, Grid2, Card, CardContent, Typography, Chip, LinearProgress, Alert, Table, TableBody, TableCell, TableContainer, TableHead, TableRow } from '@mui/material';
import { useCarteraDashboard } from '../../hooks/useCxC';
import type { PrioridadCliente } from '../../types/cxc';

// Colores semáforo por bucket
const BUCKET_COLORS: Record<string, string> = {
  al_dia: '#4caf50',
  '1_30': '#ff9800',
  '31_60': '#f57c00',
  '61_90': '#e64a19',
  mas_90: '#b71c1c',
};

const BUCKET_LABELS: Record<string, string> = {
  al_dia: 'Al Día',
  '1_30': '1-30 días',
  '31_60': '31-60 días',
  '61_90': '61-90 días',
  mas_90: '+90 días',
};

function getBucketColor(bucket: string): 'success' | 'warning' | 'error' | 'default' {
  if (bucket === 'al_dia') return 'success';
  if (bucket === '1_30') return 'warning';
  return 'error';
}

export default function DashboardCxCPage() {
  const { data, loading, error } = useCarteraDashboard();

  if (loading) return <Box p={3}><LinearProgress /></Box>;
  if (error) return <Box p={3}><Alert severity="error">{error}</Alert></Box>;
  if (!data) return null;

  const buckets = data.buckets;

  return (
    <Box p={3}>
      <Typography variant="h5" fontWeight="bold" mb={3}>
        Dashboard de Cartera
      </Typography>

      {/* KPI Cards */}
      <Grid2 container spacing={2} mb={3}>
        <Grid2 size={{ xs: 12, sm: 6, md: 3 }}>
          <Card>
            <CardContent>
              <Typography variant="body2" color="text.secondary">Total Pendiente</Typography>
              <Typography variant="h5" fontWeight="bold">
                ${parseFloat(data.total_pendiente).toLocaleString('es-VE', { minimumFractionDigits: 2 })}
              </Typography>
            </CardContent>
          </Card>
        </Grid2>
        <Grid2 size={{ xs: 12, sm: 6, md: 3 }}>
          <Card>
            <CardContent>
              <Typography variant="body2" color="text.secondary">Partidas Vencidas</Typography>
              <Typography variant="h5" fontWeight="bold" color="error">
                {data.partidas_vencidas}
              </Typography>
            </CardContent>
          </Card>
        </Grid2>
        <Grid2 size={{ xs: 12, sm: 6, md: 3 }}>
          <Card>
            <CardContent>
              <Typography variant="body2" color="text.secondary">Tasa BCV Hoy</Typography>
              <Typography variant="h5" fontWeight="bold">
                {data.tasa_bcv_hoy
                  ? `Bs. ${parseFloat(data.tasa_bcv_hoy).toLocaleString('es-VE', { minimumFractionDigits: 2 })}`
                  : 'N/D'}
              </Typography>
            </CardContent>
          </Card>
        </Grid2>
        <Grid2 size={{ xs: 12, sm: 6, md: 3 }}>
          <Card>
            <CardContent>
              <Typography variant="body2" color="text.secondary">+90 días</Typography>
              <Typography variant="h5" fontWeight="bold" color="error.dark">
                ${parseFloat(buckets.mas_90.total).toLocaleString('es-VE', { minimumFractionDigits: 2 })}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                {buckets.mas_90.count} facturas
              </Typography>
            </CardContent>
          </Card>
        </Grid2>
      </Grid2>

      {/* Aging Chart (barras simples con CSS) */}
      <Grid2 container spacing={2}>
        <Grid2 size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" fontWeight="bold" mb={2}>Aging por Bucket</Typography>
              {Object.entries(buckets).map(([key, val]) => {
                const total = parseFloat(val.total);
                const totalGeneral = parseFloat(data.total_pendiente) || 1;
                const pct = Math.min(100, (total / totalGeneral) * 100);
                return (
                  <Box key={key} mb={1.5}>
                    <Box display="flex" justifyContent="space-between" mb={0.5}>
                      <Typography variant="body2">{BUCKET_LABELS[key]}</Typography>
                      <Typography variant="body2" fontWeight="bold">
                        ${total.toLocaleString('es-VE', { minimumFractionDigits: 2 })} ({val.count})
                      </Typography>
                    </Box>
                    <LinearProgress
                      variant="determinate"
                      value={pct}
                      sx={{ height: 10, borderRadius: 5, bgcolor: '#f5f5f5', '& .MuiLinearProgress-bar': { bgcolor: BUCKET_COLORS[key] } }}
                    />
                  </Box>
                );
              })}
            </CardContent>
          </Card>
        </Grid2>

        {/* Top prioridades */}
        <Grid2 size={{ xs: 12, md: 6 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" fontWeight="bold" mb={2}>Top Prioridades</Typography>
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
                          <Typography variant="body2" fontWeight="bold">
                            ${parseFloat(p.monto_pendiente).toLocaleString('es-VE', { minimumFractionDigits: 2 })}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">{p.dias_vencida}d</TableCell>
                        <TableCell align="center">
                          <Chip label={BUCKET_LABELS[p.bucket] || p.bucket} size="small" color={getBucketColor(p.bucket)} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            </CardContent>
          </Card>
        </Grid2>
      </Grid2>
    </Box>
  );
}
