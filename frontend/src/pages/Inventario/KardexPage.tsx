import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, Button, Card, CardContent, Chip, Stack, TextField, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { productoInventarioService } from '../../services/inventarioService';
import type { MovimientoInventario } from '../../services/inventarioService';
import { PageContainer, PageHeader, DataTable } from '../../components/ui';
import type { Column } from '../../components/ui';

type ChipColor = 'success' | 'error' | 'info' | 'warning' | 'primary' | 'secondary' | 'default';

const TIPO_COLORS: Record<string, ChipColor> = {
  ENTRADA: 'success',
  RECEPCION_COMPRA: 'success',
  SALIDA: 'error',
  DESPACHO_VENTA: 'error',
  SALIDA_INTERNA: 'error',
  TRANSFERENCIA: 'info',
  AJUSTE: 'warning',
  CONSUMO_PRODUCCION: 'secondary',
  RESERVA_VENTA: 'default',
};

const ENTRADAS = new Set(['ENTRADA', 'RECEPCION_COMPRA', 'AJUSTE']);
const SALIDAS = new Set(['SALIDA', 'DESPACHO_VENTA', 'SALIDA_INTERNA', 'CONSUMO_PRODUCCION']);

const KardexPage: React.FC = () => {
  const { productoId } = useParams<{ productoId: string }>();
  const navigate = useNavigate();

  const today = new Date().toISOString().slice(0, 10);
  const sixMonthsAgo = new Date(Date.now() - 180 * 24 * 3600 * 1000).toISOString().slice(0, 10);

  const [fechaDesde, setFechaDesde] = useState(sixMonthsAgo);
  const [fechaHasta, setFechaHasta] = useState(today);

  const { data: producto } = useQuery({
    queryKey: ['producto', productoId],
    queryFn: () => productoInventarioService.getById(productoId!),
    enabled: !!productoId,
  });

  const { data: movimientos = [], isLoading } = useQuery<MovimientoInventario[]>({
    queryKey: ['kardex', productoId, fechaDesde, fechaHasta],
    queryFn: () =>
      productoInventarioService.getKardex(productoId!, {
        fecha_desde: fechaDesde,
        fecha_hasta: fechaHasta,
      }),
    enabled: !!productoId,
  });

  // Running totals for entrada/salida columns
  const totalEntradas = movimientos
    .filter((m) => ENTRADAS.has(m.tipo_movimiento))
    .reduce((sum, m) => sum + Math.abs(parseFloat(m.cantidad)), 0);

  const totalSalidas = movimientos
    .filter((m) => SALIDAS.has(m.tipo_movimiento))
    .reduce((sum, m) => sum + Math.abs(parseFloat(m.cantidad)), 0);

  const columns: Column<MovimientoInventario>[] = [
    { key: 'fecha', header: 'Fecha', render: (m) => new Date(m.fecha_hora_movimiento).toLocaleString() },
    {
      key: 'tipo',
      header: 'Tipo',
      render: (m) => <Chip size="small" label={m.tipo_movimiento.replace(/_/g, ' ')} color={TIPO_COLORS[m.tipo_movimiento] ?? 'default'} />,
    },
    {
      key: 'cantidad',
      header: 'Cantidad',
      align: 'right',
      render: (m) => {
        const isEntrada = ENTRADAS.has(m.tipo_movimiento);
        const isSalida = SALIDAS.has(m.tipo_movimiento);
        const color = isEntrada ? 'success.main' : isSalida ? 'error.main' : 'warning.main';
        const sign = isEntrada ? '+' : isSalida ? '-' : '±';
        return (
          <Typography component="span" sx={{ fontWeight: 700, color }}>
            {sign}{Math.abs(parseFloat(m.cantidad)).toLocaleString()}
          </Typography>
        );
      },
    },
    { key: 'origen', header: 'Almacén origen', render: (m) => m.almacen_origen_nombre ?? '—' },
    { key: 'destino', header: 'Almacén destino', render: (m) => m.almacen_destino_nombre ?? '—' },
    {
      key: 'costo',
      header: 'Costo unit.',
      render: (m) =>
        m.costo_unitario_movimiento
          ? parseFloat(m.costo_unitario_movimiento).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 })
          : '—',
    },
    { key: 'observaciones', header: 'Observaciones', render: (m) => m.observaciones ?? '—' },
  ];

  return (
    <PageContainer>
      <Button onClick={() => navigate('/inventario/stock')} sx={{ mb: 1 }}>
        ← Volver al stock
      </Button>
      <PageHeader
        title={`Kardex — ${producto?.nombre_producto ?? productoId}`}
        subtitle={producto ? `SKU: ${producto.sku ?? '—'} · ${producto.nombre_categoria ?? '—'} · ${producto.nombre_unidad_medida ?? '—'}` : undefined}
        actions={
          <Button variant="contained" color="warning" startIcon={<AddIcon />} onClick={() => navigate(`/inventario/ajustes?producto=${productoId}`)}>
            Ajuste
          </Button>
        }
      />

      {/* Date filter */}
      <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" useFlexGap mb={3}>
        <TextField
          type="date"
          label="Desde"
          value={fechaDesde}
          onChange={(e) => setFechaDesde(e.target.value)}
          InputLabelProps={{ shrink: true }}
          size="small"
        />
        <TextField
          type="date"
          label="Hasta"
          value={fechaHasta}
          onChange={(e) => setFechaHasta(e.target.value)}
          InputLabelProps={{ shrink: true }}
          size="small"
        />
        <Typography variant="body2" color="text.secondary">{movimientos.length} movimientos</Typography>
      </Stack>

      {/* Summary cards */}
      <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 3 }}>
        {[
          { label: 'Total entradas', value: totalEntradas.toLocaleString(), color: 'success.main' },
          { label: 'Total salidas', value: totalSalidas.toLocaleString(), color: 'error.main' },
          {
            label: 'Saldo neto',
            value: (totalEntradas - totalSalidas).toLocaleString(),
            color: totalEntradas >= totalSalidas ? 'primary.main' : 'warning.main',
          },
        ].map((c) => (
          <Card key={c.label} variant="outlined" sx={{ flex: '1 1 140px' }}>
            <CardContent>
              <Typography variant="caption" color="text.secondary">{c.label}</Typography>
              <Typography variant="h5" sx={{ fontWeight: 700, color: c.color }}>{c.value}</Typography>
            </CardContent>
          </Card>
        ))}
      </Box>

      <DataTable
        columns={columns}
        rows={movimientos}
        getRowKey={(m) => m.id_movimiento_inventario}
        loading={isLoading}
        emptyMessage="No hay movimientos en el período seleccionado."
      />
    </PageContainer>
  );
};

export default KardexPage;
