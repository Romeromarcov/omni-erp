import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Button } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { notaCreditoFiscalService } from '../../../services/ventas';
import type { NotaCreditoFiscal } from '../../../types/ventas';
import type { PaginatedResponse } from '../../../services/ventas';
import Pagination from '../../../components/Pagination';
import { PageContainer, PageHeader, DataTable } from '../../../components/ui';
import type { Column } from '../../../components/ui';

const PAGE_SIZE = 20;

export default function NotasCreditoFiscalListPage() {
  const navigate = useNavigate();
  const { t } = useTranslation();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery<PaginatedResponse<NotaCreditoFiscal>>({
    queryKey: ['notas-credito-fiscal', page],
    queryFn: () => notaCreditoFiscalService.getAllPaginated(page, PAGE_SIZE),
  });

  const notas = data?.results ?? [];
  const count = data?.count ?? 0;

  const columns: Column<NotaCreditoFiscal>[] = [
    { key: 'numero', header: t('ventas.tabla.numero'), render: (n) => n.numero_nota_credito },
    { key: 'control', header: t('ventas.facturasFiscales.tabla.control'), render: (n) => n.numero_control },
    { key: 'fecha', header: t('ventas.tabla.fecha'), render: (n) => new Date(n.fecha_emision).toLocaleDateString() },
    { key: 'motivo', header: t('ventas.notasCreditoFiscal.tabla.motivo'), render: (n) => n.motivo },
    { key: 'total', header: t('ventas.notasCreditoFiscal.tabla.total'), align: 'right', render: (n) => Number(n.monto_total ?? 0).toLocaleString('es-VE', { minimumFractionDigits: 2 }) },
    {
      key: 'acciones',
      header: t('ventas.tabla.acciones'),
      align: 'right',
      render: (n) => (
        <Button size="small" variant="outlined" onClick={(e) => { e.stopPropagation(); navigate(n.id_nota_credito_fiscal); }}>
          {t('ventas.tabla.ver')}
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('ventas.notasCreditoFiscal.title')}
        actions={
          <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('new')}>
            {t('ventas.notasCreditoFiscal.nueva')}
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={notas}
        getRowKey={(n) => n.id_nota_credito_fiscal}
        loading={isLoading}
        emptyMessage={t('ventas.notasCreditoFiscal.sinRegistros')}
        onRowClick={(n) => navigate(n.id_nota_credito_fiscal)}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={(p) => { setPage(p); window.scrollTo(0, 0); }} />
    </PageContainer>
  );
}
