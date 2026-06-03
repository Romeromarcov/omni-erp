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
import { PageContainer, PageHeader, KpiCard, DataTable } from '../../components/ui';
import type { Column } from '../../components/ui';

function stockLevel(stock: StockActual): 'critico' | 'bajo' | 'normal' {
  const disponible = parseFloat(stock.cantidad_disponible);
  const minima = parseFloat(stock.cantidad_minima);
  if (minima <= 0) return 'normal';
  if (disponible <= 0) return 'critico';
  if (disponible < minima) return 'bajo';
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
  const valorTotal = stockList.reduce((sum, s) => {
    const cantidad = parseFloat(s.cantidad_disponible);
    // If we had unit cost, we'd multiply; use available qty as proxy
    return sum + (isNaN(cantidad) ? 0 : cantidad);
  }, 0);

  const columns: Column<StockActual>[] = [
    { key: 'producto', header: 'Producto', render: (s) => s.producto_nombre ?? s.id_producto },
    { key: 'almacen', header: 'Almacén', render: (s) => s.almacen_nombre ?? '—' },
    { key: 'disponible', header: 'Disponible', render: (s) => parseFloat(s.cantidad_disponible).toLocaleString() },
    { key: 'minimo', header: 'Mínimo', render: (s) => parseFloat(s.cantidad_minima).toLocaleString() },
    { key: 'comprometido', header: 'Comprometido', render: (s) => parseFloat(s.cantidad_comprometida).toLocaleString() },
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
              value={Math.round(valorTotal).toLocaleString()}
              icon={<ScaleOutlined />}
              tone="tint"
              caption="Suma de cantidades disponibles"
            />
          </Box>

          {/* Quick actions */}
          <Stack direction="row" spacing={1.5} flexWrap="wrap" useFlexGap mb={4}>
            <Button variant="contained" onClick={() => navigate('/inventario/stock')}>Ver stock completo</Button>
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
