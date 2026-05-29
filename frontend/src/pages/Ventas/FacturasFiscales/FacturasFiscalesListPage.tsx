import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Button, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { facturaFiscalService } from '../../../services/ventas';
import type { FacturaFiscal } from '../../../types/ventas';
import type { PaginatedResponse } from '../../../services/ventas';
import Pagination from '../../../components/Pagination';
import { PageContainer, PageHeader, DataTable } from '../../../components/ui';
import type { Column } from '../../../components/ui';

const PAGE_SIZE = 20;

export default function FacturasFiscalesListPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<PaginatedResponse<FacturaFiscal>>({
    queryKey: ['facturas-fiscales', page],
    queryFn: () => facturaFiscalService.getAllPaginated(page, PAGE_SIZE),
  });

  const facturas = data?.results ?? [];
  const count = data?.count ?? 0;

  const columns: Column<FacturaFiscal>[] = [
    { key: 'numero', header: t('ventas.tabla.numero'), render: (f) => f.numero_factura },
    { key: 'fecha', header: t('ventas.tabla.fecha'), render: (f) => new Date(f.fecha_emision).toLocaleDateString() },
    { key: 'control', header: t('ventas.facturasFiscales.tabla.control'), render: (f) => f.numero_control },
    {
      key: 'cliente',
      header: t('ventas.tabla.cliente'),
      render: (f) =>
        f.id_cliente ? (
          <>
            <Typography variant="body2" fontWeight={600}>{f.id_cliente.nombre}</Typography>
            <Typography variant="caption" color="text.secondary">
              {f.id_cliente.razon_social} · {f.id_cliente.rif}
            </Typography>
          </>
        ) : (
          <Typography variant="body2" color="error">{t('ventas.tabla.clienteNoEncontrado')}</Typography>
        ),
    },
    {
      key: 'total',
      header: t('ventas.facturasFiscales.tabla.total'),
      align: 'right',
      render: (f) => Number(f.monto_total ?? 0).toLocaleString('es-VE', { minimumFractionDigits: 2 }),
    },
    {
      key: 'acciones',
      header: t('ventas.tabla.acciones'),
      align: 'right',
      render: (f) => (
        <Button size="small" variant="outlined" onClick={(e) => { e.stopPropagation(); navigate(f.id_factura); }}>
          {t('ventas.tabla.ver')}
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('ventas.facturasFiscales.title')}
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('new')}>
            {t('ventas.facturasFiscales.nueva')}
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={facturas}
        getRowKey={(f) => f.id_factura}
        loading={isLoading}
        emptyMessage={t('ventas.facturasFiscales.sinRegistros')}
        onRowClick={(f) => navigate(f.id_factura)}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={(p) => { setPage(p); window.scrollTo(0, 0); }} />
    </PageContainer>
  );
}
