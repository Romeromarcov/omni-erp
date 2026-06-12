/**
 * Listado de Órdenes de Producción (1.I) — punto de entrada del módulo de
 * manufactura: desde aquí se navega al detalle con etapas, costeo real y MRP.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Button, Typography } from '@mui/material';
import { manufacturaService } from '../../services/manufacturaService';
import type { OrdenProduccion } from '../../services/manufacturaService';
import { manufacturaKeys } from '../../lib/queryKeys';
import { toFixedStr } from '../../lib/decimal';
import Pagination from '../../components/Pagination';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';

const PAGE_SIZE = 20;

export default function OrdenesProduccionListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: manufacturaKeys.ordenes(page),
    queryFn: () => manufacturaService.getOrdenesPaginated(page, PAGE_SIZE),
  });

  const ordenes = data?.results ?? [];
  const count = data?.count ?? 0;

  const columns: Column<OrdenProduccion>[] = [
    {
      key: 'referencia',
      header: t('manufactura.ordenes.title'),
      render: (o) => (
        <Typography variant="body2" fontWeight={600}>
          {o.referencia_externa || `OF-${o.id.slice(0, 8)}`}
        </Typography>
      ),
    },
    { key: 'cantidad', header: t('manufactura.ordenes.cantidad'), align: 'right', render: (o) => toFixedStr(o.cantidad) },
    { key: 'fecha_inicio', header: t('manufactura.ordenes.fechaInicio'), render: (o) => o.fecha_inicio },
    {
      key: 'estado',
      header: t('manufactura.ordenes.estado'),
      render: (o) => <StatusChip value={o.estado} />,
    },
    {
      key: 'acciones',
      header: t('common.actions'),
      render: (o) => (
        <Button size="small" onClick={() => navigate(`/manufactura/ordenes/${o.id}`)}>
          {t('manufactura.ordenes.ver')}
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader title={t('manufactura.ordenes.title')} subtitle={t('manufactura.ordenes.subtitle')} />
      <DataTable
        columns={columns}
        rows={ordenes}
        getRowKey={(o) => o.id}
        loading={isLoading}
        emptyMessage={t('manufactura.ordenes.empty')}
        onRowClick={(o) => navigate(`/manufactura/ordenes/${o.id}`)}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={setPage} />
    </PageContainer>
  );
}
