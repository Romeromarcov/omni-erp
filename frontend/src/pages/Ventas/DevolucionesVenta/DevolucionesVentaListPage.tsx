import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Button } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { devolucionVentaService } from '../../../services/ventas';
import type { DevolucionVenta } from '../../../types/ventas';
import type { PaginatedResponse } from '../../../services/ventas';
import Pagination from '../../../components/Pagination';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../../components/ui';
import type { Column } from '../../../components/ui';

const PAGE_SIZE = 20;

export default function DevolucionesVentaListPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<PaginatedResponse<DevolucionVenta>>({
    queryKey: ['devoluciones-venta', page],
    queryFn: () => devolucionVentaService.getAllPaginated(page, PAGE_SIZE),
  });

  const devoluciones = data?.results ?? [];
  const count = data?.count ?? 0;

  const columns: Column<DevolucionVenta>[] = [
    { key: 'numero', header: t('ventas.tabla.numero'), render: (d) => d.numero_devolucion },
    { key: 'fecha', header: t('ventas.tabla.fecha'), render: (d) => new Date(d.fecha_devolucion).toLocaleDateString() },
    { key: 'motivo', header: t('ventas.devoluciones.tabla.motivo'), render: (d) => d.motivo_devolucion },
    { key: 'monto', header: t('ventas.devoluciones.tabla.total'), align: 'right', render: (d) => Number(d.monto_total ?? 0).toLocaleString('es-VE', { minimumFractionDigits: 2 }) },
    { key: 'estado', header: t('ventas.tabla.estado'), render: (d) => <StatusChip value={d.estado} /> },
    {
      key: 'acciones',
      header: t('ventas.tabla.acciones'),
      align: 'right',
      render: (d) => (
        <Button size="small" variant="outlined" onClick={(e) => { e.stopPropagation(); navigate(d.id_devolucion); }}>
          {t('ventas.tabla.ver')}
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('ventas.devoluciones.title')}
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('new')}>
            {t('ventas.devoluciones.nueva')}
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={devoluciones}
        getRowKey={(d) => d.id_devolucion}
        loading={isLoading}
        emptyMessage={t('ventas.devoluciones.sinRegistros')}
        onRowClick={(d) => navigate(d.id_devolucion)}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={(p) => { setPage(p); window.scrollTo(0, 0); }} />
    </PageContainer>
  );
}
