import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Button, Stack, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { pedidoService } from '../../../services/ventas';
import type { Pedido } from '../../../types/ventas';
import type { PaginatedResponse } from '../../../services/ventas';
import Pagination from '../../../components/Pagination';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../../components/ui';
import type { Column } from '../../../components/ui';

const PAGE_SIZE = 20;

export default function PedidosListPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { t } = useTranslation();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<PaginatedResponse<Pedido>>({
    queryKey: ['pedidos', page],
    queryFn: () => pedidoService.getAllPaginated(page, PAGE_SIZE),
  });

  const pedidos = data?.results ?? [];
  const count = data?.count ?? 0;

  const convertirMutation = useMutation({
    mutationFn: (pedidoId: string) => pedidoService.convertirANotaVenta(pedidoId, {}),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['pedidos'] }),
    onError: () => alert(t('ventas.pedidos.errorConvertir')),
  });

  const columns: Column<Pedido>[] = [
    { key: 'numero', header: t('ventas.tabla.numero'), render: (p) => p.numero_pedido },
    {
      key: 'fecha',
      header: t('ventas.tabla.fecha'),
      render: (p) => new Date(p.fecha_pedido).toLocaleDateString(),
    },
    { key: 'estado', header: t('ventas.tabla.estado'), render: (p) => <StatusChip value={p.estado} /> },
    {
      key: 'cliente',
      header: t('ventas.tabla.cliente'),
      render: (p) =>
        p.id_cliente ? (
          <>
            <Typography variant="body2" fontWeight={600}>{p.id_cliente.nombre}</Typography>
            <Typography variant="caption" color="text.secondary">
              {p.id_cliente.razon_social} · {p.id_cliente.rif}
            </Typography>
          </>
        ) : (
          <Typography variant="body2" color="error">{t('ventas.tabla.clienteNoEncontrado')}</Typography>
        ),
    },
    {
      key: 'origen',
      header: t('ventas.tabla.origen'),
      render: (p) =>
        p.id_cotizacion_origen ? (
          <StatusChip value="convertido" label={t('ventas.pedidos.deCotizacion')} />
        ) : (
          <Typography variant="caption" color="text.secondary">{t('ventas.tabla.manual')}</Typography>
        ),
    },
    {
      key: 'acciones',
      header: t('ventas.tabla.acciones'),
      align: 'right',
      render: (p) => (
        <Stack direction="row" spacing={1} justifyContent="flex-end" onClick={(e) => e.stopPropagation()}>
          <Button size="small" variant="outlined" onClick={() => navigate(p.id_pedido)}>
            {t('ventas.tabla.ver')}
          </Button>
          <Button size="small" variant="outlined" onClick={() => navigate(`${p.id_pedido}/edit`)}>
            {t('common.edit')}
          </Button>
          {!p.convertido_a_nota_venta && p.estado === 'APROBADO' && (
            <Button
              size="small"
              variant="contained"
              disabled={convertirMutation.isPending}
              onClick={() => convertirMutation.mutate(p.id_pedido)}
            >
              {t('ventas.pedidos.convertirANotaVenta')}
            </Button>
          )}
          {p.convertido_a_nota_venta && <StatusChip value="convertido" label={t('ventas.tabla.convertido')} />}
        </Stack>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('ventas.pedidos.title')}
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('new')}>
            {t('ventas.pedidos.nuevo')}
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={pedidos}
        getRowKey={(p) => p.id_pedido}
        loading={isLoading}
        emptyMessage={t('ventas.pedidos.sinRegistros')}
        onRowClick={(p) => navigate(p.id_pedido)}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={(p) => { setPage(p); window.scrollTo(0, 0); }} />
    </PageContainer>
  );
}
