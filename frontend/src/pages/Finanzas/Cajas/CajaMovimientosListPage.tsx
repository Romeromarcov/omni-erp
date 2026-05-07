import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import PageLayout from '../../../components/PageLayout';
import { getMovimientosCaja } from '../../../services/cajaService';
import { Button, TextField } from '@mui/material';

type MovimientoCaja = {
  id_movimiento: string;
  fecha_movimiento: string;
  hora_movimiento: string;
  tipo_movimiento: string;
  monto: number | string;
  id_moneda__codigo_iso?: string;
  moneda_codigo_iso?: string;
  concepto: string;
  referencia: string;
  id_caja__nombre_caja?: string;
  caja_nombre?: string;
  sucursal_nombre?: string;
  empresa_nombre?: string;
  saldo_anterior: number | string;
  saldo_nuevo: number | string;
  id_usuario_registro__username?: string;
  usuario_registro_username?: string;
};

const CajaMovimientosListPage: React.FC = () => {
  const { id_caja } = useParams<{ id_caja: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<MovimientoCaja[]>([]);
  const [filters, setFilters] = useState({ fecha_inicio: '', fecha_fin: '', tipo: '', moneda: '', concepto: '', referencia: '', usuario: '' });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!id_caja) return;
    setLoading(true);
    getMovimientosCaja(id_caja, filters)
      .then(result => {
        if (Array.isArray(result)) {
          setData(result);
        } else if (
          result &&
          typeof result === 'object' &&
          'results' in result &&
          Array.isArray((result as { results: MovimientoCaja[] }).results)
        ) {
          setData((result as { results: MovimientoCaja[] }).results);
        } else {
          setData([]);
        }
      })
      .finally(() => setLoading(false));
  }, [id_caja, filters]);

  // Extraer info de la caja si hay datos
  const cajaNombre = data[0]?.caja_nombre || '-';
  const sucursalNombre = data[0]?.sucursal_nombre || '-';
  const empresaNombre = data[0]?.empresa_nombre || '-';

  return (
    <PageLayout maxWidth={1600}>
      <h2 style={{ marginBottom: 16 }}>
        Movimientos de Caja
        <span style={{ fontSize: 16, fontWeight: 400, marginLeft: 16, color: '#555' }}>
          {cajaNombre !== '-' && (
            <>
              | <b>{cajaNombre}</b>
              {sucursalNombre !== '-' && <> &nbsp;| Sucursal: <b>{sucursalNombre}</b></>}
              {empresaNombre !== '-' && <> &nbsp;| Empresa: <b>{empresaNombre}</b></>}
            </>
          )}
        </span>
      </h2>
      <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <TextField fullWidth type="date" label="Desde" value={filters.fecha_inicio} onChange={e => setFilters(f => ({ ...f, fecha_inicio: e.target.value }))} />
        <TextField fullWidth type="date" label="Hasta" value={filters.fecha_fin} onChange={e => setFilters(f => ({ ...f, fecha_fin: e.target.value }))} />
        <TextField fullWidth placeholder="Tipo" value={filters.tipo} onChange={e => setFilters(f => ({ ...f, tipo: e.target.value }))} />
        <TextField fullWidth placeholder="Moneda" value={filters.moneda} onChange={e => setFilters(f => ({ ...f, moneda: e.target.value }))} />
        <TextField fullWidth placeholder="Concepto" value={filters.concepto} onChange={e => setFilters(f => ({ ...f, concepto: e.target.value }))} />
        <TextField fullWidth placeholder="Referencia" value={filters.referencia} onChange={e => setFilters(f => ({ ...f, referencia: e.target.value }))} />
        <TextField fullWidth placeholder="Usuario" value={filters.usuario} onChange={e => setFilters(f => ({ ...f, usuario: e.target.value }))} />
        <Button variant="outlined" onClick={() => setFilters({ fecha_inicio: '', fecha_fin: '', tipo: '', moneda: '', concepto: '', referencia: '', usuario: '' })}>Limpiar</Button>
        <Button variant="contained" onClick={() => { /* TODO: exportar informe */ }}>Exportar</Button>
        <Button variant="outlined" onClick={() => navigate(-1)}>Volver</Button>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th>Fecha</th>
              <th>Hora</th>
              <th>Tipo</th>
              <th>Monto</th>
              <th>Moneda</th>
              <th>Concepto</th>
              <th>Referencia</th>
              <th>Caja</th>
              <th>Saldo Anterior</th>
              <th>Saldo Nuevo</th>
              <th>Usuario</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={11} style={{ textAlign: 'center' }}>Cargando...</td></tr>
            ) : data.length === 0 ? (
              <tr><td colSpan={11} style={{ textAlign: 'center' }}>No hay movimientos registrados.</td></tr>
            ) : data.map((row) => (
              <tr key={row.id_movimiento}>
                <td>{row.fecha_movimiento}</td>
                <td>{row.hora_movimiento}</td>
                <td>{row.tipo_movimiento}</td>
                <td>{Number(row.monto).toFixed(2)}</td>
                <td>{row.moneda_codigo_iso || '-'}</td>
                <td>{row.concepto}</td>
                <td>{row.referencia}</td>
                <td>{row.caja_nombre || '-'}</td>
                <td>{Number(row.saldo_anterior).toFixed(2)}</td>
                <td>{Number(row.saldo_nuevo).toFixed(2)}</td>
                <td>{row.usuario_registro_username || '-'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PageLayout>
  );
};

export default CajaMovimientosListPage;
