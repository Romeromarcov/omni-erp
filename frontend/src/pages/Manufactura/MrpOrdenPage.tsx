/**
 * MRP básico de la OF (1.I): explosión de la BOM vs StockActual (disponible
 * neto) → tabla de faltantes a comprar. El cálculo se dispara con el botón
 * "Calcular MRP" (query lazy con TanStack: enabled solo tras la acción).
 */
import { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Alert, Button, CircularProgress, MenuItem, Stack, TextField, Typography } from '@mui/material';
import CalculateOutlined from '@mui/icons-material/CalculateOutlined';
import { manufacturaService } from '../../services/manufacturaService';
import type { MrpFaltante } from '../../services/manufacturaService';
import { almacenesService } from '../../services/almacenesService';
import { manufacturaKeys, almacenesKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';
import { toFixedStr } from '../../lib/decimal';
import { PageContainer, PageHeader, DataTable } from '../../components/ui';
import type { Column } from '../../components/ui';

export default function MrpOrdenPage() {
  const { id = '' } = useParams<{ id: string }>();
  const { t } = useTranslation();
  const navigate = useNavigate();

  const [almacenId, setAlmacenId] = useState('');
  const [calculado, setCalculado] = useState(false);

  const { data: almacenes = [] } = useQuery({
    queryKey: almacenesKeys.all(),
    queryFn: () => almacenesService.getAll(),
  });

  const { data, isFetching, error, refetch } = useQuery({
    queryKey: manufacturaKeys.mrp(id, almacenId || null),
    queryFn: () => manufacturaService.getMrp(id, { almacenId: almacenId || undefined }),
    enabled: false,
  });

  const calcular = () => {
    setCalculado(true);
    void refetch();
  };

  const columns: Column<MrpFaltante>[] = [
    {
      key: 'producto',
      header: t('manufactura.mrp.producto'),
      render: (f) => (
        <Typography variant="body2" fontWeight={600}>
          {f.producto || f.producto_id}
        </Typography>
      ),
    },
    { key: 'requerido', header: t('manufactura.mrp.requerido'), align: 'right', render: (f) => toFixedStr(f.requerido) },
    { key: 'disponible', header: t('manufactura.mrp.disponible'), align: 'right', render: (f) => toFixedStr(f.disponible) },
    {
      key: 'a_comprar',
      header: t('manufactura.mrp.aComprar'),
      align: 'right',
      render: (f) => (
        <Typography variant="body2" fontWeight={700} color="error.main">
          {toFixedStr(f.a_comprar)}
        </Typography>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title={t('manufactura.mrp.title')}
        subtitle={t('manufactura.mrp.subtitle')}
        actions={
          <Button variant="outlined" onClick={() => navigate(`/manufactura/ordenes/${id}`)}>
            {t('common.back')}
          </Button>
        }
      />

      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3 }} alignItems="flex-start">
        <TextField
          select
          size="small"
          label={t('manufactura.mrp.almacen')}
          value={almacenId}
          onChange={(e) => setAlmacenId(e.target.value)}
          sx={{ minWidth: 240 }}
        >
          <MenuItem value="">{t('manufactura.mrp.todos')}</MenuItem>
          {almacenes.map((a) => (
            <MenuItem key={a.id_almacen} value={a.id_almacen}>
              {a.nombre_almacen}
            </MenuItem>
          ))}
        </TextField>
        <Button
          variant="contained"
          startIcon={<CalculateOutlined />}
          onClick={calcular}
          disabled={isFetching}
        >
          {calculado ? t('manufactura.mrp.recalcular') : t('manufactura.mrp.calcular')}
        </Button>
      </Stack>

      {isFetching && (
        <Stack alignItems="center" sx={{ py: 6 }}>
          <CircularProgress />
        </Stack>
      )}

      {!isFetching && calculado && error != null && (
        <Alert severity="error">{mensajeDeError(error, t('manufactura.mrp.error'))}</Alert>
      )}

      {!isFetching && !error && data && (
        data.faltantes.length === 0 ? (
          <Alert severity="success">{t('manufactura.mrp.sinFaltantes')}</Alert>
        ) : (
          <DataTable
            columns={columns}
            rows={data.faltantes}
            getRowKey={(f) => f.producto_id}
            emptyMessage={t('manufactura.comun.sinDatos')}
          />
        )
      )}
    </PageContainer>
  );
}
