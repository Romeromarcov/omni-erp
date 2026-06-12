/**
 * Listado de Órdenes de Compra (workstream F) — punto de entrada del módulo
 * de compras: desde aquí se navega al detalle (líneas, recepción, factura)
 * y al formulario de creación de OC.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Button, Typography } from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { comprasService } from '../../services/comprasService';
import type { OrdenCompra } from '../../services/comprasService';
import { comprasKeys } from '../../lib/queryKeys';
import Pagination from '../../components/Pagination';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';

const PAGE_SIZE = 20;

export default function OrdenesCompraListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: comprasKeys.ordenes(page),
    queryFn: () => comprasService.getOrdenesPaginated(page, PAGE_SIZE),
  });

  const ordenes = data?.results ?? [];
  const count = data?.count ?? 0;

  const columns: Column<OrdenCompra>[] = [
    {
      key: 'numero',
      header: t('compras.ordenes.numero'),
      render: (o) => (
        <Typography variant="body2" fontWeight={600}>
          {o.numero_orden}
        </Typography>
      ),
    },
    { key: 'fecha', header: t('compras.ordenes.fecha'), render: (o) => o.fecha_orden },
    {
      key: 'estado',
      header: t('compras.ordenes.estado'),
      render: (o) => <StatusChip value={o.estado} />,
    },
    {
      key: 'acciones',
      header: t('common.actions'),
      align: 'right',
      render: (o) => (
        <Button size="small" onClick={() => navigate(`/compras/ordenes/${o.id_orden_compra}`)}>
          {t('compras.ordenes.ver')}
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('compras.ordenes.title')}
        subtitle={t('compras.ordenes.subtitle')}
        actions={
          <Button variant="contained" startIcon={<AddOutlined />} onClick={() => navigate('/compras/ordenes/nueva')}>
            {t('compras.ordenes.nueva')}
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={ordenes}
        getRowKey={(o) => o.id_orden_compra}
        loading={isLoading}
        emptyMessage={t('compras.ordenes.empty')}
        onRowClick={(o) => navigate(`/compras/ordenes/${o.id_orden_compra}`)}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={setPage} />
    </PageContainer>
  );
}
