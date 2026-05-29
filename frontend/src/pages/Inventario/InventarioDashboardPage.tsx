import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, Card, CardActionArea, CardContent, Chip, Stack, Typography } from '@mui/material';
import { stockActualService, productoInventarioService } from '../../services/inventarioService';
import type { StockActual } from '../../services/inventarioService';
import { PageContainer, PageHeader, DataTable } from '../../components/ui';
import type { Column } from '../../components/ui';

// ── KPI Card ──────────────────────────────────────────────────────────────

interface KpiCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  color?: string;
  onClick?: () => void;
}

const KpiCard: React.FC<KpiCardProps> = ({ title, value, subtitle, color = 'primary.main', onClick }) => {
  const inner = (
    <CardContent>
      <Typography variant="body2" color="text.secondary" gutterBottom>{title}</Typography>
      <Typography variant="h4" sx={{ fontWeight: 700, color }}>{value}</Typography>
      {subtitle && <Typography variant="caption" color="text.secondary">{subtitle}</Typography>}
    </CardContent>
  );
  return (
    <Card variant="outlined" sx={{ flex: '1 1 160px' }}>
      {onClick ? <CardActionArea onClick={onClick}>{inner}</CardActionArea> : inner}
    </Card>
  );
};

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
    queryKey: ['stock-actual-all'],
    queryFn: () => stockActualService.getAll(),
  });

  const { data: productos = [], isLoading: loadingProductos } = useQuery({
    queryKey: ['productos-inventario'],
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
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 2, mb: 4 }}>
            <KpiCard title="Productos registrados" value={totalSKUs} subtitle="SKUs activos" onClick={() => navigate('/inventario/stock')} />
            <KpiCard title="Alertas de stock" value={alertas.length} subtitle="Por debajo del mínimo" color={alertas.length > 0 ? 'warning.main' : 'success.main'} />
            <KpiCard title="Stock crítico" value={criticos.length} subtitle="Cantidad = 0" color={criticos.length > 0 ? 'error.main' : 'success.main'} />
            <KpiCard title="Unidades totales" value={Math.round(valorTotal).toLocaleString()} subtitle="Suma de cantidades disponibles" color="secondary.main" />
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
