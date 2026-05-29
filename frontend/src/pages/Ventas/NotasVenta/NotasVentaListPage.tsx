import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Button, Stack, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { notaVentaService } from '../../../services/ventas';
import type { NotaVenta } from '../../../types/ventas';
import type { PaginatedResponse } from '../../../services/ventas';
import Pagination from '../../../components/Pagination';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../../components/ui';
import type { Column } from '../../../components/ui';

const PAGE_SIZE = 20;

export default function NotasVentaListPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<PaginatedResponse<NotaVenta>>({
    queryKey: ['notas-venta', page],
    queryFn: () => notaVentaService.getAllPaginated(page, PAGE_SIZE),
  });

  const notasVenta = data?.results ?? [];
  const count = data?.count ?? 0;

  const columns: Column<NotaVenta>[] = [
    { key: 'numero', header: t('ventas.tabla.numero'), render: (n) => n.numero_nota_venta },
    { key: 'fecha', header: t('ventas.tabla.fecha'), render: (n) => new Date(n.fecha_nota_venta).toLocaleDateString() },
    { key: 'estado', header: t('ventas.tabla.estado'), render: (n) => <StatusChip value={n.estado} /> },
    {
      key: 'cliente',
      header: t('ventas.tabla.cliente'),
      render: (n) =>
        n.id_cliente ? (
          <>
            <Typography variant="body2" fontWeight={600}>{n.id_cliente.nombre}</Typography>
            <Typography variant="caption" color="text.secondary">
              {n.id_cliente.razon_social} · {n.id_cliente.rif}
            </Typography>
          </>
        ) : (
          <Typography variant="body2" color="error">{t('ventas.tabla.clienteNoEncontrado')}</Typography>
        ),
    },
    {
      key: 'acciones',
      header: t('ventas.tabla.acciones'),
      align: 'right',
      render: (n) => (
        <Stack direction="row" spacing={1} justifyContent="flex-end" onClick={(e) => e.stopPropagation()}>
          <Button size="small" variant="outlined" onClick={() => navigate(n.id_nota_venta)}>{t('ventas.tabla.ver')}</Button>
          {n.estado !== 'FACTURADA' && (
            <Button size="small" variant="outlined" onClick={() => navigate(`${n.id_nota_venta}/edit`)}>{t('common.edit')}</Button>
          )}
        </Stack>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('ventas.notasVenta.title')}
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('new')}>
            {t('ventas.notasVenta.nueva')}
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={notasVenta}
        getRowKey={(n) => n.id_nota_venta}
        loading={isLoading}
        emptyMessage={t('ventas.notasVenta.sinRegistros')}
        onRowClick={(n) => navigate(n.id_nota_venta)}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={(p) => { setPage(p); window.scrollTo(0, 0); }} />
    </PageContainer>
  );
}
