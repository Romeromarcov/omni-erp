import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import PageLayout from '../../components/PageLayout';
import { stockActualService, productoInventarioService } from '../../services/inventarioService';
import type { StockActual } from '../../services/inventarioService';

function stockBadgeColor(stock: StockActual): { label: string; color: string } {
  const disponible = parseFloat(stock.cantidad_disponible);
  const minima = parseFloat(stock.cantidad_minima);
  if (disponible <= 0) return { label: 'SIN STOCK', color: '#f44336' };
  if (minima > 0 && disponible < minima) return { label: 'BAJO', color: '#ff9800' };
  return { label: 'NORMAL', color: '#4caf50' };
}

const StockActualPage: React.FC = () => {
  const navigate = useNavigate();
  const [filtroProducto, setFiltroProducto] = useState('');
  const [filtroAlmacen, setFiltroAlmacen] = useState('');
  const [soloAlertas, setSoloAlertas] = useState(false);

  const { data: stockList = [], isLoading } = useQuery<StockActual[]>({
    queryKey: ['stock-actual-all'],
    queryFn: () => stockActualService.getAll(),
  });

  const { data: productos = [] } = useQuery({
    queryKey: ['productos-inventario'],
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
  const totalUnidades = stockList.reduce((sum, s) => sum + parseFloat(s.cantidad_disponible), 0);

  return (
    <PageLayout maxWidth={1200}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
        <div>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>Stock Actual</h2>
          <p style={{ color: '#6c757d', margin: '4px 0 0', fontSize: 14 }}>
            {totalProductos} productos · {Math.round(totalUnidades).toLocaleString()} unidades totales
          </p>
        </div>
        <div style={{ display: 'flex', gap: 10 }}>
          <button
            onClick={() => navigate('/inventario')}
            style={{
              padding: '8px 16px',
              background: 'transparent',
              border: '1px solid #dee2e6',
              borderRadius: 8,
              cursor: 'pointer',
              fontSize: 14,
            }}
          >
            Dashboard
          </button>
          <button
            onClick={() => navigate('/inventario/ajustes')}
            style={{
              padding: '8px 16px',
              background: '#1976d2',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              cursor: 'pointer',
              fontWeight: 600,
              fontSize: 14,
            }}
          >
            + Ajuste manual
          </button>
        </div>
      </div>

      {/* Filters */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap', alignItems: 'center' }}>
        <input
          type="text"
          placeholder="Buscar producto…"
          value={filtroProducto}
          onChange={(e) => setFiltroProducto(e.target.value)}
          style={{
            padding: '8px 12px',
            border: '1px solid #dee2e6',
            borderRadius: 8,
            fontSize: 14,
            minWidth: 200,
          }}
        />
        <select
          value={filtroAlmacen}
          onChange={(e) => setFiltroAlmacen(e.target.value)}
          style={{
            padding: '8px 12px',
            border: '1px solid #dee2e6',
            borderRadius: 8,
            fontSize: 14,
            minWidth: 160,
          }}
        >
          <option value="">Todos los almacenes</option>
          {almacenes.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>
        <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: 14, cursor: 'pointer' }}>
          <input
            type="checkbox"
            checked={soloAlertas}
            onChange={(e) => setSoloAlertas(e.target.checked)}
          />
          Solo alertas
        </label>
        <span style={{ fontSize: 13, color: '#6c757d' }}>{filtered.length} registros</span>
      </div>

      {/* Table */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#6c757d' }}>Cargando stock…</div>
      ) : filtered.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#6c757d' }}>
          No hay registros con los filtros seleccionados.
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: '#f8f9fa' }}>
                {[
                  'Producto',
                  'Almacén',
                  'Disponible',
                  'Mínimo',
                  'Máximo',
                  'Comprometido',
                  'En tránsito',
                  'Estado',
                  'Acciones',
                ].map((h) => (
                  <th
                    key={h}
                    style={{ padding: '10px 12px', textAlign: 'left', borderBottom: '2px solid #dee2e6' }}
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filtered.map((s) => {
                const badge = stockBadgeColor(s);
                return (
                  <tr
                    key={s.id_stock_actual}
                    style={{ borderBottom: '1px solid #dee2e6' }}
                  >
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
                      {parseFloat(s.cantidad_maxima).toLocaleString()}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      {parseFloat(s.cantidad_comprometida).toLocaleString()}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      {parseFloat(s.cantidad_en_transito).toLocaleString()}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <span
                        style={{
                          padding: '3px 10px',
                          borderRadius: 6,
                          backgroundColor: badge.color,
                          color: '#fff',
                          fontSize: 11,
                          fontWeight: 600,
                        }}
                      >
                        {badge.label}
                      </span>
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      <div style={{ display: 'flex', gap: 8 }}>
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
                            whiteSpace: 'nowrap',
                          }}
                        >
                          Kardex
                        </button>
                        <button
                          onClick={() =>
                            navigate(`/inventario/ajustes?producto=${s.id_producto}&almacen=${s.id_almacen}`)
                          }
                          style={{
                            padding: '4px 12px',
                            background: 'transparent',
                            border: '1px solid #ff9800',
                            color: '#ff9800',
                            borderRadius: 6,
                            cursor: 'pointer',
                            fontSize: 13,
                            whiteSpace: 'nowrap',
                          }}
                        >
                          Ajuste
                        </button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Last updated */}
      {stockList.length > 0 && (
        <p style={{ fontSize: 12, color: '#adb5bd', marginTop: 16, textAlign: 'right' }}>
          Última actualización:{' '}
          {new Date(
            stockList.reduce((latest, s) =>
              s.fecha_ultima_actualizacion > latest.fecha_ultima_actualizacion ? s : latest
            ).fecha_ultima_actualizacion
          ).toLocaleString()}
        </p>
      )}
    </PageLayout>
  );
};

export default StockActualPage;
