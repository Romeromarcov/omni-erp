/**
 * Libro de asientos contables (workstream F) — lista paginada con filtros por
 * estado y rango de fechas; navega al detalle con líneas debe/haber.
 */
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Button, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { contabilidadService } from '../../services/contabilidadService';
import type { AsientoContable } from '../../services/contabilidadService';
import { contabilidadKeys } from '../../lib/queryKeys';
import Pagination from '../../components/Pagination';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';

const PAGE_SIZE = 20;
const ESTADOS = ['BORRADOR', 'APROBADO', 'ANULADO'] as const;

export default function AsientosContablesListPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [page, setPage] = useState(1);
  const [estado, setEstado] = useState('');
  const [fechaDesde, setFechaDesde] = useState('');
  const [fechaHasta, setFechaHasta] = useState('');

  const filtros = { estado, fechaDesde, fechaHasta };
  const { data, isLoading } = useQuery({
    queryKey: contabilidadKeys.asientos(page, filtros),
    queryFn: () => contabilidadService.getAsientosPaginated(page, PAGE_SIZE, filtros),
  });

  const asientos = data?.results ?? [];
  const count = data?.count ?? 0;

  const columns: Column<AsientoContable>[] = [
    {
      key: 'numero',
      header: t('contabilidad.asientos.numero'),
      render: (a) => (
        <Typography variant="body2" fontWeight={600}>
          {a.numero_asiento}
        </Typography>
      ),
    },
    { key: 'fecha', header: t('contabilidad.asientos.fecha'), render: (a) => a.fecha_asiento },
    { key: 'descripcion', header: t('contabilidad.asientos.descripcion'), render: (a) => a.descripcion },
    {
      key: 'origen',
      header: t('contabilidad.asientos.origen'),
      render: (a) => a.nombre_modelo_origen || t('contabilidad.asientos.manual'),
    },
    {
      key: 'estado',
      header: t('contabilidad.asientos.estado'),
      render: (a) => <StatusChip value={a.estado_asiento} />,
    },
    {
      key: 'acciones',
      header: t('common.actions'),
      render: (a) => (
        <Button size="small" onClick={() => navigate(`/contabilidad/asientos/${a.id_asiento}`)}>
          {t('contabilidad.asientos.ver')}
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader title={t('contabilidad.asientos.title')} subtitle={t('contabilidad.asientos.subtitle')} />
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 2 }}>
        <TextField
          select
          size="small"
          label={t('contabilidad.asientos.estado')}
          value={estado}
          onChange={(e) => {
            setEstado(e.target.value);
            setPage(1);
          }}
          sx={{ minWidth: 180 }}
        >
          <MenuItem value="">{t('contabilidad.asientos.todos')}</MenuItem>
          {ESTADOS.map((e) => (
            <MenuItem key={e} value={e}>
              {e}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          size="small"
          type="date"
          label={t('contabilidad.asientos.desde')}
          value={fechaDesde}
          InputLabelProps={{ shrink: true }}
          onChange={(e) => {
            setFechaDesde(e.target.value);
            setPage(1);
          }}
        />
        <TextField
          size="small"
          type="date"
          label={t('contabilidad.asientos.hasta')}
          value={fechaHasta}
          InputLabelProps={{ shrink: true }}
          onChange={(e) => {
            setFechaHasta(e.target.value);
            setPage(1);
          }}
        />
      </Stack>
      <DataTable
        columns={columns}
        rows={asientos}
        getRowKey={(a) => a.id_asiento}
        loading={isLoading}
        emptyMessage={t('contabilidad.asientos.empty')}
        onRowClick={(a) => navigate(`/contabilidad/asientos/${a.id_asiento}`)}
      />
      <Pagination page={page} count={count} pageSize={PAGE_SIZE} onChange={setPage} />
    </PageContainer>
  );
}
