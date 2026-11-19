import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, Chip, Stack, Typography } from '@mui/material';
import InventoryOutlined from '@mui/icons-material/InventoryOutlined';
import WarningAmberOutlined from '@mui/icons-material/WarningAmberOutlined';
import ErrorOutlineOutlined from '@mui/icons-material/ErrorOutlineOutlined';
import ScaleOutlined from '@mui/icons-material/ScaleOutlined';
import { stockActualService, productoInventarioService } from '../../services/inventarioService';
import type { StockActual } from '../../services/inventarioService';
import { inventarioKeys } from '../../lib/queryKeys';
import { D, formatoDecimal, sumDecimals } from '../../lib/decimal';
import { PageContainer, PageHeader, KpiCard, DataTable } from '../../components/ui';
import type { Column } from '../../components/ui';

function stockLevel(stock: StockActual): 'critico' | 'bajo' | 'normal' {
  const disponible = D(stock.cantidad_disponible);
  const minima = D(stock.cantidad_minima);
  if (minima.lte(0)) return 'normal';
  if (disponible.lte(0)) return 'critico';
  if (disponible.lt(minima)) return 'bajo';
  return 'normal';
}

// ── Page ──────────────────────────────────────────────────────────────────

const InventarioDashboardPage: React.FC = () => {
  const navigate = useNavigate();

  const { data: stockList = [], isLoading: loadingStock } = useQuery<StockActual[]>({
    queryKey: inventarioKeys.stockActualAll(),
    queryFn: () => stockActualService.getAll(),
  });

  const { data: productos = [], isLoading: loadingProductos } = useQuery({
    queryKey: inventarioKeys.productosInventario(),
    queryFn: () => productoInventarioService.getAll(),
  });

  const isLoading = loadingStock || loadingProductos;

  // KPI calculations
  const totalSKUs = productos.length;
  const alertas = stockList.filter((s) => stockLevel(s) !== 'normal');
  const criticos = stockList.filter((s) => stockLevel(s) === 'critico');
  const valorTotal = sumDecimals(stockList.map((s) => s.cantidad_disponible));

  const columns: Column<StockActual>[] = [
    { key: 'producto', header: 'Producto', render: (s) => s.producto_nombre ?? s.id_producto },
    { key: 'almacen', header: 'Almacén', render: (s) => s.almacen_nombre ?? '—' },
    { key: 'disponible', header: 'Disponible', render: (s) => formatoDecimal(s.cantidad_disponible, 0, 4) },
    { key: 'minimo', header: 'Mínimo', render: (s) => formatoDecimal(s.cantidad_minima, 0, 4) },
    { key: 'comprometido', header: 'Comprometido', render: (s) => formatoDecimal(s.cantidad_comprometida, 0, 4) },
    {
      key: 'estado',
      header: 'Estado',
      render: (s) => {
        const nivel = stockLevel(s);
        return <Chip size="small" label={nivel === 'critico' ? 'SIN STOCK' : 'BAJO'} color={nivel === 'critico' ? 'error' : 'warning'} />;
      },
    },
    {
      key: 'accion',
      header: 'Acción',
      align: 'right',
      render: (s) => (
        <Button size="small" variant="outlined" onClick={() => navigate(`/inventario/kardex/${s.id_producto}`)}>
          Kardex
        </Button>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader title="Dashboard de Inventario" subtitle="Resumen de stock actual, alertas y KPIs del inventario." />

      {isLoading ? (
        <DataTable columns={columns} rows={[]} getRowKey={(s) => s.id_stock_actual} loading />
      ) : (
        <>
          {/* KPI Cards */}
          <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(4, 1fr)' }, gap: 2, mb: 4 }}>
            <KpiCard
              label="Productos registrados"
              value={totalSKUs}
              icon={<InventoryOutlined />}
              tone="brand"
              caption="SKUs activos"
            />
            <KpiCard
              label="Alertas de stock"
              value={alertas.length}
              icon={<WarningAmberOutlined />}
              tone={alertas.length > 0 ? 'warning' : 'success'}
              caption="Por debajo del mínimo"
              emphasizeError={alertas.length > 0}
            />
            <KpiCard
              label="Stock crítico"
              value={criticos.length}
              icon={<ErrorOutlineOutlined />}
              tone={criticos.length > 0 ? 'error' : 'success'}
              caption="Cantidad = 0"
              emphasizeError={criticos.length > 0}
            />
            <KpiCard
              label="Unidades totales"
              value={formatoDecimal(valorTotal.toDecimalPlaces(0), 0, 0)}
              icon={<ScaleOutlined />}
              tone="tint"
              caption="Suma de cantidades disponibles"
            />
          </Box>

          {/* Quick actions */}
          <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap mb={4}>
            <Button variant="contained" onClick={() => navigate('/inventario/stock')}>Ver stock completo</Button>
            <Button variant="outlined" onClick={() => navigate('/inventario/productos')}>Productos</Button>
            <Button variant="outlined" onClick={() => navigate('/inventario/almacenes')}>Almacenes</Button>
            <Button variant="outlined" onClick={() => navigate('/inventario/ajustes')}>Registrar ajuste</Button>
          </Stack>

          {/* Alert table */}
          {alertas.length === 0 ? (
            <Alert severity="success">Todos los productos están sobre el stock mínimo</Alert>
          ) : (
            <>
              <Typography variant="h6" mb={1.5}>Alertas de stock ({alertas.length})</Typography>
              <DataTable
                columns={columns}
                rows={alertas}
                getRowKey={(s) => s.id_stock_actual}
                emptyMessage="No hay alertas de stock."
              />
            </>
          )}
        </>
      )}
    </PageContainer>
  );
};

export default InventarioDashboardPage;
