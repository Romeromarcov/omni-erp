import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Button, Stack, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { cotizacionService } from '../../../services/ventas';
import type { Cotizacion } from '../../../types/ventas';
import type { PaginatedResponse } from '../../../services/ventas';
import Pagination from '../../../components/Pagination';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../../components/ui';
import type { Column } from '../../../components/ui';

const PAGE_SIZE = 20;

export default function CotizacionesListPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<PaginatedResponse<Cotizacion>>({
    queryKey: ['cotizaciones', page],
    queryFn: () => cotizacionService.getAllPaginated(page, PAGE_SIZE),
  });

  const cotizaciones = data?.results ?? [];
  const count = data?.count ?? 0;

  const columns: Column<Cotizacion>[] = [
    { key: 'numero', header: t('ventas.tabla.numero'), render: (c) => c.numero_cotizacion },
    { key: 'fecha', header: t('ventas.tabla.fecha'), render: (c) => new Date(c.fecha_cotizacion).toLocaleDateString() },
    { key: 'estado', header: t('ventas.tabla.estado'), render: (c) => <StatusChip value={c.estado} /> },
    {
      key: 'cliente',
      header: t('ventas.tabla.cliente'),
      render: (c) =>
        c.id_cliente ? (
          <>
            <Typography variant="body2" fontWeight={600}>{c.id_cliente.nombre}</Typography>
            <Typography variant="caption" color="text.secondary">
              {c.id_cliente.razon_social} · {c.id_cliente.rif}
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
      render: (c) => (
        <Stack direction="row" spacing={1} justifyContent="flex-end" onClick={(e) => e.stopPropagation()}>
          <Button size="small" variant="outlined" onClick={() => navigate(c.id_cotizacion)}>{t('ventas.tabla.ver')}</Button>
          <Button size="small" variant="outlined" onClick={() => navigate(`${c.id_cotizacion}/edit`)}>{t('common.edit')}</Button>
        </Stack>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('ventas.cotizaciones.title')}
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('new')}>
            {t('ventas.cotizaciones.nueva')}
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={cotizaciones}
        getRowKey={(c) => c.id_cotizacion}
        loading={isLoading}
        emptyMessage={t('ventas.cotizaciones.sinRegistros')}
        onRowClick={(c) => navigate(c.id_cotizacion)}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={(p) => { setPage(p); window.scrollTo(0, 0); }} />
    </PageContainer>
  );
}
