import React, { useState } from 'react';
import { D, sumDecimals } from '../../lib/decimal';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Box, Button, Chip, FormControlLabel, Checkbox, MenuItem, Stack, TextField, Typography } from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import { stockActualService, productoInventarioService } from '../../services/inventarioService';
import type { StockActual } from '../../services/inventarioService';
import { PageContainer, PageHeader, DataTable } from '../../components/ui';
import type { Column } from '../../components/ui';
import { inventarioKeys } from '../../lib/queryKeys';

type ChipColor = 'error' | 'warning' | 'success';

function stockBadge(stock: StockActual): { label: string; color: ChipColor } {
  const disponible = parseFloat(stock.cantidad_disponible);
  const minima = parseFloat(stock.cantidad_minima);
  if (disponible <= 0) return { label: 'SIN STOCK', color: 'error' };
  if (minima > 0 && disponible < minima) return { label: 'BAJO', color: 'warning' };
  return { label: 'NORMAL', color: 'success' };
}

const StockActualPage: React.FC = () => {
  const navigate = useNavigate();
  const [filtroProducto, setFiltroProducto] = useState('');
  const [filtroAlmacen, setFiltroAlmacen] = useState('');
  const [soloAlertas, setSoloAlertas] = useState(false);

  const { data: stockList = [], isLoading } = useQuery<StockActual[]>({
    queryKey: inventarioKeys.stockActualAll(),
    queryFn: () => stockActualService.getAll(),
  });

  const { data: productos = [] } = useQuery({
    queryKey: inventarioKeys.productosInventario(),
    queryFn: () => productoInventarioService.getAll(),
  });

  // Collect unique warehouse names for filter dropdown
  const almacenes = [...new Set(stockList.map((s) => s.almacen_nombre).filter(Boolean))] as string[];

  // Apply filters
  const filtered = stockList.filter((s) => {
    const nombre = (s.producto_nombre ?? '').toLowerCase();
    const matchProducto = filtroProducto === '' || nombre.includes(filtroProducto.toLowerCase());
    const matchAlmacen = filtroAlmacen === '' || s.almacen_nombre === filtroAlmacen;
    const matchAlerta = !soloAlertas || parseFloat(s.cantidad_disponible) < parseFloat(s.cantidad_minima);
    return matchProducto && matchAlmacen && matchAlerta;
  });

  const totalProductos = productos.length;
  const totalUnidades = sumDecimals(stockList.map((s) => D(s.cantidad_disponible))).toNumber();

  const columns: Column<StockActual>[] = [
    { key: 'producto', header: 'Producto', render: (s) => s.producto_nombre ?? s.id_producto },
    { key: 'almacen', header: 'Almacén', render: (s) => s.almacen_nombre ?? '—' },
    { key: 'disponible', header: 'Disponible', render: (s) => parseFloat(s.cantidad_disponible).toLocaleString() },
    { key: 'minimo', header: 'Mínimo', render: (s) => parseFloat(s.cantidad_minima).toLocaleString() },
    { key: 'maximo', header: 'Máximo', render: (s) => parseFloat(s.cantidad_maxima).toLocaleString() },
    { key: 'comprometido', header: 'Comprometido', render: (s) => parseFloat(s.cantidad_comprometida).toLocaleString() },
    { key: 'transito', header: 'En tránsito', render: (s) => parseFloat(s.cantidad_en_transito).toLocaleString() },
    {
      key: 'estado',
      header: 'Estado',
      render: (s) => {
        const badge = stockBadge(s);
        return <Chip size="small" label={badge.label} color={badge.color} />;
      },
    },
    {
      key: 'acciones',
      header: 'Acciones',
      align: 'right',
      render: (s) => (
        <Stack direction="row" spacing={1} justifyContent="flex-end">
          <Button size="small" variant="outlined" onClick={() => navigate(`/inventario/kardex/${s.id_producto}`)}>
            Kardex
          </Button>
          <Button size="small" variant="outlined" color="warning" onClick={() => navigate(`/inventario/ajustes?producto=${s.id_producto}&almacen=${s.id_almacen}`)}>
            Ajuste
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Stock Actual"
        subtitle={`${totalProductos} productos · ${Math.round(totalUnidades).toLocaleString()} unidades totales`}
        actions={
          <>
            <Button variant="outlined" onClick={() => navigate('/inventario')}>Dashboard</Button>
            <Button variant="contained" startIcon={<AddIcon />} onClick={() => navigate('/inventario/ajustes')}>Ajuste manual</Button>
          </>
        }
      />
      <Box sx={{ mb: 2 }}>
        <Stack direction="row" flexWrap="wrap" gap={1.5} alignItems="center" useFlexGap>
          <TextField
            size="small"
            placeholder="Buscar producto…"
            value={filtroProducto}
            onChange={(e) => setFiltroProducto(e.target.value)}
            sx={{ minWidth: 200 }}
          />
          <TextField
            select
            size="small"
            value={filtroAlmacen}
            onChange={(e) => setFiltroAlmacen(e.target.value)}
            sx={{ minWidth: 160 }}
          >
            <MenuItem value="">Todos los almacenes</MenuItem>
            {almacenes.map((a) => (
              <MenuItem key={a} value={a}>{a}</MenuItem>
            ))}
          </TextField>
          <FormControlLabel
            control={<Checkbox checked={soloAlertas} onChange={(e) => setSoloAlertas(e.target.checked)} />}
            label="Solo alertas"
          />
          <Typography variant="body2" color="text.secondary">{filtered.length} registros</Typography>
        </Stack>
      </Box>
      <DataTable
        columns={columns}
        rows={filtered}
        getRowKey={(s) => s.id_stock_actual}
        loading={isLoading}
        emptyMessage="No hay registros con los filtros seleccionados."
      />
      {stockList.length > 0 && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 2, textAlign: 'right' }}>
          Última actualización:{' '}
          {new Date(
            stockList.reduce((latest, s) =>
              s.fecha_ultima_actualizacion > latest.fecha_ultima_actualizacion ? s : latest
            ).fecha_ultima_actualizacion
          ).toLocaleString()}
        </Typography>
      )}
    </PageContainer>
  );
};

export default StockActualPage;
