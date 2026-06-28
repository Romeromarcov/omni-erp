/**
 * Cartera / Devoluciones — CxC Lubrikca (Fase 6b).
 *
 * Vista de visibilidad (solo lectura): KPIs de cartera atascada y pedidos con
 * devolución (del resumen), la lista de pedidos con devolución, y la lista de
 * pedidos no facturados con entrega antigua (proxy de cartera atascada).
 */
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Box, Typography } from '@mui/material';
import WarningAmberOutlined from '@mui/icons-material/WarningAmberOutlined';
import AssignmentReturnOutlined from '@mui/icons-material/AssignmentReturnOutlined';
import { cxcLubrikcaService } from '../../services/cxcLubrikcaService';
import type { Pedido } from '../../services/cxcLubrikcaService';
import { cxcLubrikcaKeys } from '../../lib/queryKeys';
import { PageContainer, PageHeader, DataTable, StatusChip, KpiCard, SectionTitle } from '../../components/ui';
import type { Column } from '../../components/ui';

const money = (v: string | number) =>
  `$${parseFloat(String(v)).toLocaleString('es-VE', { minimumFractionDigits: 2 })}`;

// Días de antigüedad de entrega para considerar un pedido no facturado como
// cartera atascada (espejo del DIAS_CARTERA_ATASCADA del backend).
const DIAS_ATASCADA = 30;

function esAtascada(p: Pedido): boolean {
  if (p.facturada || !p.fecha_entrega) return false;
  const entrega = new Date(p.fecha_entrega);
  if (Number.isNaN(entrega.getTime())) return false;
  const limite = Date.now() - DIAS_ATASCADA * 24 * 60 * 60 * 1000;
  return entrega.getTime() < limite;
}

const pedidoColumns: Column<Pedido>[] = [
  { key: 'so', header: 'Pedido (SO)', render: (p) => p.so_id },
  { key: 'cliente', header: 'Cliente', render: (p) => p.cliente_nombre || '—' },
  { key: 'monto', header: 'Monto total', align: 'right', render: (p) => money(p.monto_total) },
  { key: 'entrega', header: 'Fecha entrega', render: (p) => p.fecha_entrega || '—' },
  { key: 'estado', header: 'Entrega', render: (p) => <StatusChip value={p.estado_entrega} /> },
  { key: 'facturada', header: 'Facturada', render: (p) => <StatusChip value={p.facturada} /> },
];

export default function CarteraPage() {
  const { data: resumen } = useQuery({
    queryKey: cxcLubrikcaKeys.resumen(),
    queryFn: () => cxcLubrikcaService.getResumen(),
  });

  const { data: pedidos = [], isLoading } = useQuery({
    queryKey: cxcLubrikcaKeys.pedidosAll(),
    queryFn: () => cxcLubrikcaService.listPedidos(),
  });

  const conDevolucion = useMemo(() => pedidos.filter((p) => p.tiene_devolucion), [pedidos]);
  const atascados = useMemo(() => pedidos.filter(esAtascada), [pedidos]);

  return (
    <PageContainer>
      <PageHeader title="Cartera y Devoluciones" subtitle="Visibilidad de cartera atascada y devoluciones" />

      <Box
        sx={{
          display: 'grid',
          gap: 2,
          gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' },
          mb: 4,
        }}
      >
        <KpiCard
          label="Cartera atascada"
          value={resumen?.cartera_atascada ?? 0}
          tone="warning"
          icon={<WarningAmberOutlined />}
        />
        <KpiCard
          label="Pedidos con devolución"
          value={resumen?.pedidos_con_devolucion ?? 0}
          tone="tint"
          icon={<AssignmentReturnOutlined />}
        />
        <KpiCard label="Facturados sin conciliar" value={resumen?.facturados_sin_conciliar ?? 0} tone="tint" />
        <KpiCard
          label="Diferencia total"
          value={money(resumen?.diferencia_total ?? '0')}
          tone="error"
        />
      </Box>

      <SectionTitle>Pedidos con devolución</SectionTitle>
      <Box sx={{ mb: 4 }}>
        <DataTable
          columns={pedidoColumns}
          rows={conDevolucion}
          getRowKey={(p) => p.id}
          loading={isLoading}
          emptyMessage="No hay pedidos con devolución."
        />
      </Box>

      <SectionTitle>Cartera atascada (no facturados con entrega antigua)</SectionTitle>
      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
        Pedidos entregados hace más de {DIAS_ATASCADA} días sin facturar.
      </Typography>
      <DataTable
        columns={pedidoColumns}
        rows={atascados}
        getRowKey={(p) => p.id}
        loading={isLoading}
        emptyMessage="No hay cartera atascada."
      />
    </PageContainer>
  );
}
