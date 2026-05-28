import React from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import PageLayout from '../../components/PageLayout';
import { stockActualService, productoInventarioService } from '../../services/inventarioService';
import type { StockActual } from '../../services/inventarioService';

// ── KPI Card ──────────────────────────────────────────────────────────────

interface KpiCardProps {
  title: string;
  value: string | number;
  subtitle?: string;
  color?: string;
  onClick?: () => void;
}

const KpiCard: React.FC<KpiCardProps> = ({ title, value, subtitle, color = '#1976d2', onClick }) => (
  <div
    onClick={onClick}
    style={{
      background: '#fff',
      border: `2px solid ${color}`,
      borderRadius: 12,
      padding: '20px 24px',
      minWidth: 160,
      flex: 1,
      cursor: onClick ? 'pointer' : 'default',
      boxShadow: '0 2px 8px rgba(0,0,0,0.06)',
      transition: 'box-shadow 0.2s',
    }}
  >
    <div style={{ fontSize: 13, color: '#6c757d', marginBottom: 4 }}>{title}</div>
    <div style={{ fontSize: 32, fontWeight: 700, color }}>{value}</div>
    {subtitle && <div style={{ fontSize: 12, color: '#adb5bd', marginTop: 4 }}>{subtitle}</div>}
  </div>
);

// ── Badge ─────────────────────────────────────────────────────────────────

const Badge: React.FC<{ label: string; color: string }> = ({ label, color }) => (
  <span
    style={{
      padding: '3px 10px',
      borderRadius: 6,
      backgroundColor: color,
      color: '#fff',
      fontSize: 11,
      fontWeight: 600,
      letterSpacing: 0.3,
    }}
  >
    {label}
  </span>
);

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

  return (
    <PageLayout maxWidth={1100}>
      <div style={{ marginBottom: 24 }}>
        <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Dashboard de Inventario</h2>
        <p style={{ color: '#6c757d', margin: '4px 0 0', fontSize: 14 }}>
          Resumen de stock actual, alertas y KPIs del inventario.
        </p>
      </div>

      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#6c757d' }}>Cargando inventario…</div>
      ) : (
        <>
          {/* KPI Cards */}
          <div style={{ display: 'flex', gap: 16, flexWrap: 'wrap', marginBottom: 32 }}>
            <KpiCard
              title="Productos registrados"
              value={totalSKUs}
              subtitle="SKUs activos"
              color="#1976d2"
              onClick={() => navigate('/inventario/stock')}
            />
            <KpiCard
              title="Alertas de stock"
              value={alertas.length}
              subtitle="Por debajo del mínimo"
              color={alertas.length > 0 ? '#ff9800' : '#4caf50'}
            />
            <KpiCard
              title="Stock crítico"
              value={criticos.length}
              subtitle="Cantidad = 0"
              color={criticos.length > 0 ? '#f44336' : '#4caf50'}
            />
            <KpiCard
              title="Unidades totales"
              value={Math.round(valorTotal).toLocaleString()}
              subtitle="Suma de cantidades disponibles"
              color="#9c27b0"
            />
          </div>

          {/* Quick actions */}
          <div style={{ display: 'flex', gap: 12, marginBottom: 32, flexWrap: 'wrap' }}>
            <button
              onClick={() => navigate('/inventario/stock')}
              style={{
                padding: '10px 20px',
                background: '#1976d2',
                color: '#fff',
                border: 'none',
                borderRadius: 8,
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: 14,
              }}
            >
              Ver stock completo
            </button>
            <button
              onClick={() => navigate('/inventario/ajustes')}
              style={{
                padding: '10px 20px',
                background: '#fff',
                color: '#1976d2',
                border: '2px solid #1976d2',
                borderRadius: 8,
                cursor: 'pointer',
                fontWeight: 600,
                fontSize: 14,
              }}
            >
              Registrar ajuste
            </button>
          </div>

          {/* Alert table */}
          {alertas.length === 0 ? (
            <div
              style={{
                textAlign: 'center',
                padding: '32px',
                background: '#f1f8e9',
                borderRadius: 12,
                color: '#388e3c',
                fontWeight: 600,
              }}
            >
              ✅ Todos los productos están sobre el stock mínimo
            </div>
          ) : (
            <>
              <h3 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12 }}>
                ⚠️ Alertas de stock ({alertas.length})
              </h3>
              <div style={{ overflowX: 'auto' }}>
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
                  <thead>
                    <tr style={{ background: '#f8f9fa' }}>
                      {['Producto', 'Almacén', 'Disponible', 'Mínimo', 'Comprometido', 'Estado', 'Acción'].map(
                        (h) => (
                          <th
                            key={h}
                            style={{ padding: '10px 12px', textAlign: 'left', borderBottom: '2px solid #dee2e6' }}
                          >
                            {h}
                          </th>
                        )
                      )}
                    </tr>
                  </thead>
                  <tbody>
                    {alertas.map((s) => {
                      const nivel = stockLevel(s);
                      return (
                        <tr key={s.id_stock_actual} style={{ borderBottom: '1px solid #dee2e6' }}>
                          <td style={{ padding: '10px 12px', fontWeight: 500 }}>
                            {s.producto_nombre ?? s.id_producto}
                          </td>
                          <td style={{ padding: '10px 12px', color: '#6c757d' }}>
                            {s.almacen_nombre ?? '—'}
                          </td>
                          <td style={{ padding: '10px 12px', fontWeight: 700 }}>
                            {parseFloat(s.cantidad_disponible).toLocaleString()}
                          </td>
                          <td style={{ padding: '10px 12px' }}>
                            {parseFloat(s.cantidad_minima).toLocaleString()}
                          </td>
                          <td style={{ padding: '10px 12px' }}>
                            {parseFloat(s.cantidad_comprometida).toLocaleString()}
                          </td>
                          <td style={{ padding: '10px 12px' }}>
                            <Badge
                              label={nivel === 'critico' ? 'SIN STOCK' : 'BAJO'}
                              color={nivel === 'critico' ? '#f44336' : '#ff9800'}
                            />
                          </td>
                          <td style={{ padding: '10px 12px' }}>
                            <button
                              onClick={() => navigate(`/inventario/kardex/${s.id_producto}`)}
                              style={{
                                padding: '4px 12px',
                                background: 'transparent',
                                border: '1px solid #1976d2',
                                color: '#1976d2',
                                borderRadius: 6,
                                cursor: 'pointer',
                                fontSize: 13,
                              }}
                            >
                              Kardex
                            </button>
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </>
          )}
        </>
      )}
    </PageLayout>
  );
};

export default InventarioDashboardPage;
