/**
 * Operaciones de cambio de divisa (workstream F) — lista paginada con montos
 * y tasa en string decimal (R-CODE-4); creación en formulario dedicado.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Button, Typography } from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import { tesoreriaService } from '../../services/tesoreriaService';
import type { OperacionCambioDivisa } from '../../services/tesoreriaService';
import { tesoreriaKeys } from '../../lib/queryKeys';
import { toFixedStr } from '../../lib/decimal';
import Pagination from '../../components/Pagination';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';

const PAGE_SIZE = 20;

export default function OperacionesCambioListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);

  const { data, isLoading } = useQuery({
    queryKey: tesoreriaKeys.operacionesCambio(page),
    queryFn: () => tesoreriaService.getOperacionesCambioPaginated(page, PAGE_SIZE),
  });

  const operaciones = data?.results ?? [];
  const count = data?.count ?? 0;

  const columns: Column<OperacionCambioDivisa>[] = [
    {
      key: 'numero',
      header: t('tesoreria.cambioDivisa.numero'),
      render: (o) => (
        <Typography variant="body2" fontWeight={600}>
          {o.numero_operacion}
        </Typography>
      ),
    },
    {
      key: 'fecha',
      header: t('tesoreria.cambioDivisa.fecha'),
      render: (o) => o.fecha_operacion?.slice(0, 10) ?? '—',
    },
    {
      key: 'tipo',
      header: t('tesoreria.cambioDivisa.tipo'),
      render: (o) => <StatusChip value={o.tipo_operacion} />,
    },
    {
      key: 'montoOrigen',
      header: t('tesoreria.cambioDivisa.montoOrigen'),
      align: 'right',
      render: (o) => toFixedStr(o.monto_origen, 4),
    },
    {
      key: 'tasa',
      header: t('tesoreria.cambioDivisa.tasa'),
      align: 'right',
      render: (o) => toFixedStr(o.tasa_cambio, 6),
    },
    {
      key: 'montoDestino',
      header: t('tesoreria.cambioDivisa.montoDestino'),
      align: 'right',
      render: (o) => toFixedStr(o.monto_destino, 4),
    },
    {
      key: 'comision',
      header: t('tesoreria.cambioDivisa.comision'),
      align: 'right',
      render: (o) => toFixedStr(o.comision, 4),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('tesoreria.cambioDivisa.title')}
        subtitle={t('tesoreria.cambioDivisa.subtitle')}
        actions={
          <Button
            variant="contained"
            startIcon={<AddOutlined />}
            onClick={() => navigate('/tesoreria/cambio-divisa/nueva')}
          >
            {t('tesoreria.cambioDivisa.nueva')}
          </Button>
        }
      />
      <DataTable
        columns={columns}
        rows={operaciones}
        getRowKey={(o) => String(o.id)}
        loading={isLoading}
        emptyMessage={t('tesoreria.cambioDivisa.empty')}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={setPage} />
    </PageContainer>
  );
}
