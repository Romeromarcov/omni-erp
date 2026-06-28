/**
 * Dashboard de cartera del subproyecto CxC Lubrikca.
 *
 * Lee el resumen agregado (GET /cxc-lubrikca/conciliaciones/resumen/) y lo
 * presenta como tarjetas KPI: semáforo verde/amarillo/rojo, facturados sin
 * conciliar, pedidos con devolución, cartera atascada, candidatas sin aprobar y
 * la diferencia total acumulada. El botón "Sincronizar Odoo" dispara el espejo.
 */
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { Box, Button, CircularProgress } from '@mui/material';
import SyncOutlined from '@mui/icons-material/SyncOutlined';
import { cxcLubrikcaService } from '../../services/cxcLubrikcaService';
import { cxcLubrikcaKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { useSnackbar } from '../../contexts/feedbackTypes';
import { PageContainer, PageHeader, KpiCard } from '../../components/ui';

const money = (v: string | number) =>
  `$${parseFloat(String(v)).toLocaleString('es-VE', { minimumFractionDigits: 2 })}`;

export default function DashboardCxcLubrikcaPage() {
  const queryClient = useQueryClient();
  const snackbar = useSnackbar();

  const { data, isLoading } = useQuery({
    queryKey: cxcLubrikcaKeys.resumen(),
    queryFn: () => cxcLubrikcaService.getResumen(),
  });

  const sincronizar = useMutation({
    mutationFn: () => cxcLubrikcaService.sincronizarPedidos(),
    onSuccess: () => {
      snackbar.success('Sincronización con Odoo completada.');
      queryClient.invalidateQueries({ queryKey: cxcLubrikcaKeys.all() });
    },
    onError: (err: unknown) => {
      snackbar.error(mensajeDeError(err, 'Error al sincronizar con Odoo.'));
    },
  });

  const semaforo = data?.por_resultado ?? { verde: 0, amarillo: 0, rojo: 0 };

  return (
    <PageContainer>
      <PageHeader
        title="Cartera Lubrikca"
        subtitle="Resumen del motor de cobranza y conciliación"
        actions={
          <Button
            variant="contained"
            startIcon={
              sincronizar.isPending ? <CircularProgress size={16} color="inherit" /> : <SyncOutlined />
            }
            disabled={sincronizar.isPending}
            onClick={() => sincronizar.mutate()}
          >
            Sincronizar Odoo
          </Button>
        }
      />

      {isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
          <CircularProgress />
        </Box>
      ) : (
        <Box
          sx={{
            display: 'grid',
            gap: 2,
            gridTemplateColumns: { xs: '1fr', sm: '1fr 1fr', md: 'repeat(4, 1fr)' },
          }}
        >
          <KpiCard label="Conciliadas verde" value={semaforo.verde} tone="success" />
          <KpiCard label="Conciliadas amarillo" value={semaforo.amarillo} tone="warning" />
          <KpiCard label="Conciliadas rojo" value={semaforo.rojo} tone="error" />
          <KpiCard
            label="Facturados sin conciliar"
            value={data?.facturados_sin_conciliar ?? 0}
            tone="tint"
          />
          <KpiCard
            label="Pedidos con devolución"
            value={data?.pedidos_con_devolucion ?? 0}
            tone="tint"
          />
          <KpiCard label="Cartera atascada" value={data?.cartera_atascada ?? 0} tone="warning" />
          <KpiCard
            label="Candidatas sin aprobar"
            value={data?.bandejas_candidatas_sin_aprobar ?? 0}
            tone="tint"
          />
          <KpiCard
            label="Diferencia total"
            value={money(data?.diferencia_total ?? '0')}
            tone="error"
            emphasizeError={parseFloat(data?.diferencia_total ?? '0') !== 0}
          />
        </Box>
      )}
    </PageContainer>
  );
}
