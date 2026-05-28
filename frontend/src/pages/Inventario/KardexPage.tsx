import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import PageLayout from '../../components/PageLayout';
import { productoInventarioService } from '../../services/inventarioService';
import type { MovimientoInventario } from '../../services/inventarioService';

const TIPO_COLORS: Record<string, string> = {
  ENTRADA: '#4caf50',
  RECEPCION_COMPRA: '#66bb6a',
  SALIDA: '#f44336',
  DESPACHO_VENTA: '#ef5350',
  SALIDA_INTERNA: '#e53935',
  TRANSFERENCIA: '#2196f3',
  AJUSTE: '#ff9800',
  CONSUMO_PRODUCCION: '#9c27b0',
  RESERVA_VENTA: '#607d8b',
};

function tipoBadge(tipo: string) {
  const color = TIPO_COLORS[tipo] ?? '#6c757d';
  return (
    <span
      style={{
        padding: '3px 10px',
        borderRadius: 6,
        backgroundColor: color,
        color: '#fff',
        fontSize: 11,
        fontWeight: 600,
        whiteSpace: 'nowrap',
      }}
    >
      {tipo.replace(/_/g, ' ')}
    </span>
  );
}

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

  return (
    <PageLayout maxWidth={1100}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 20 }}>
        <div>
          <button
            onClick={() => navigate('/inventario/stock')}
            style={{
              background: 'none',
              border: 'none',
              color: '#1976d2',
              cursor: 'pointer',
              fontSize: 14,
              padding: 0,
              marginBottom: 6,
            }}
          >
            ← Volver al stock
          </button>
          <h2 style={{ margin: 0, fontSize: 22, fontWeight: 700 }}>
            Kardex — {producto?.nombre_producto ?? productoId}
          </h2>
          {producto && (
            <p style={{ color: '#6c757d', margin: '4px 0 0', fontSize: 14 }}>
              SKU: {producto.sku ?? '—'} · {producto.nombre_categoria ?? '—'} ·{' '}
              {producto.nombre_unidad_medida ?? '—'}
            </p>
          )}
        </div>
        <button
          onClick={() => navigate(`/inventario/ajustes?producto=${productoId}`)}
          style={{
            padding: '8px 16px',
            background: '#ff9800',
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            cursor: 'pointer',
            fontWeight: 600,
            fontSize: 14,
          }}
        >
          + Ajuste
        </button>
      </div>

      {/* Date filter */}
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, alignItems: 'center', flexWrap: 'wrap' }}>
        <label style={{ fontSize: 14 }}>
          Desde:{' '}
          <input
            type="date"
            value={fechaDesde}
            onChange={(e) => setFechaDesde(e.target.value)}
            style={{ padding: '6px 10px', border: '1px solid #dee2e6', borderRadius: 6, fontSize: 14 }}
          />
        </label>
        <label style={{ fontSize: 14 }}>
          Hasta:{' '}
          <input
            type="date"
            value={fechaHasta}
            onChange={(e) => setFechaHasta(e.target.value)}
            style={{ padding: '6px 10px', border: '1px solid #dee2e6', borderRadius: 6, fontSize: 14 }}
          />
        </label>
        <span style={{ fontSize: 13, color: '#6c757d' }}>
          {movimientos.length} movimientos
        </span>
      </div>

      {/* Summary cards */}
      <div style={{ display: 'flex', gap: 16, marginBottom: 24, flexWrap: 'wrap' }}>
        {[
          { label: 'Total entradas', value: totalEntradas.toLocaleString(), color: '#4caf50' },
          { label: 'Total salidas', value: totalSalidas.toLocaleString(), color: '#f44336' },
          {
            label: 'Saldo neto',
            value: (totalEntradas - totalSalidas).toLocaleString(),
            color: totalEntradas >= totalSalidas ? '#1976d2' : '#ff9800',
          },
        ].map((c) => (
          <div
            key={c.label}
            style={{
              flex: 1,
              minWidth: 140,
              padding: '14px 18px',
              border: `2px solid ${c.color}`,
              borderRadius: 10,
              background: '#fff',
            }}
          >
            <div style={{ fontSize: 12, color: '#6c757d', marginBottom: 2 }}>{c.label}</div>
            <div style={{ fontSize: 24, fontWeight: 700, color: c.color }}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* Movement table */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#6c757d' }}>Cargando movimientos…</div>
      ) : movimientos.length === 0 ? (
        <div style={{ textAlign: 'center', padding: 40, color: '#6c757d' }}>
          No hay movimientos en el período seleccionado.
        </div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 14 }}>
            <thead>
              <tr style={{ background: '#f8f9fa' }}>
                {['Fecha', 'Tipo', 'Cantidad', 'Almacén origen', 'Almacén destino', 'Costo unit.', 'Observaciones'].map(
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
              {movimientos.map((m) => {
                const isEntrada = ENTRADAS.has(m.tipo_movimiento);
                const cantNum = parseFloat(m.cantidad);
                return (
                  <tr key={m.id_movimiento_inventario} style={{ borderBottom: '1px solid #dee2e6' }}>
                    <td style={{ padding: '10px 12px', whiteSpace: 'nowrap' }}>
                      {new Date(m.fecha_hora_movimiento).toLocaleString()}
                    </td>
                    <td style={{ padding: '10px 12px' }}>{tipoBadge(m.tipo_movimiento)}</td>
                    <td
                      style={{
                        padding: '10px 12px',
                        fontWeight: 700,
                        color: isEntrada ? '#4caf50' : SALIDAS.has(m.tipo_movimiento) ? '#f44336' : '#ff9800',
                      }}
                    >
                      {isEntrada ? '+' : SALIDAS.has(m.tipo_movimiento) ? '-' : '±'}
                      {Math.abs(cantNum).toLocaleString()}
                    </td>
                    <td style={{ padding: '10px 12px', color: '#6c757d' }}>
                      {m.almacen_origen_nombre ?? '—'}
                    </td>
                    <td style={{ padding: '10px 12px', color: '#6c757d' }}>
                      {m.almacen_destino_nombre ?? '—'}
                    </td>
                    <td style={{ padding: '10px 12px' }}>
                      {m.costo_unitario_movimiento
                        ? parseFloat(m.costo_unitario_movimiento).toLocaleString(undefined, {
                            minimumFractionDigits: 2,
                            maximumFractionDigits: 4,
                          })
                        : '—'}
                    </td>
                    <td style={{ padding: '10px 12px', color: '#6c757d', maxWidth: 200 }}>
                      {m.observaciones ?? '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </PageLayout>
  );
};

export default KardexPage;
