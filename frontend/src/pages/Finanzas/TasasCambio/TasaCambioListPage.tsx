
import React, { useEffect, useState } from 'react';
interface TasaOficialBCV {
  fecha_tasa: string;
  valor_tasa: string;
}
import { useParams, useNavigate } from 'react-router-dom';
import { get } from '../../../services/api';
import { fetchMonedas } from '../../../services/monedas';
import type { Moneda } from '../../../services/monedas';
import PageLayout from '../../../components/PageLayout';
import { Button } from '@mui/material';

interface TasaCambio {
  id_tasa_cambio: string;
  fecha_tasa: string;
  id_moneda_origen: string;
  id_moneda_origen__codigo_iso?: string;
  id_moneda_destino: string;
  id_moneda_destino__codigo_iso?: string;
  tipo_tasa: string;
  valor_tasa: string;
  id_usuario_registro__username?: string;
  moneda_origen_nombre?: string;
  moneda_destino_nombre?: string;
  usuario_registro_username?: string;
}

const TasaCambioListPage: React.FC = () => {
  const [tasaOficial, setTasaOficial] = useState<TasaOficialBCV | null>(null);
  const [loadingTasaOficial, setLoadingTasaOficial] = useState(true);
  const [errorTasaOficial, setErrorTasaOficial] = useState('');
  // Cargar tasa oficial BCV global USD/VES del día
  useEffect(() => {
    setLoadingTasaOficial(true);
    get('/finanzas/tasa-oficial-bcv/?moneda_origen=USD&moneda_destino=VES')
      .then((data) => {
        setTasaOficial(data as TasaOficialBCV);
        setErrorTasaOficial('');
      })
      .catch(() => {
        setTasaOficial(null);
        setErrorTasaOficial('No hay tasa oficial BCV registrada para hoy.');
      })
      .finally(() => setLoadingTasaOficial(false));
  }, []);
  const { id_empresa } = useParams();
  const navigate = useNavigate();
  const [tasas, setTasas] = useState<TasaCambio[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [filtros, setFiltros] = useState({ moneda_origen: '', moneda_destino: '', fecha: '' });
  const [count, setCount] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  // Cargar monedas para los dropdowns
  useEffect(() => {
    fetchMonedas().then(setMonedas);
  }, []);

  type TasaCambioApiResponse = { count: number; results: TasaCambio[] } | TasaCambio[];
  useEffect(() => {
    setLoading(true);
    let url = `/finanzas/tasas-cambio/?id_empresa=${id_empresa}&limit=${pageSize}&offset=${(page-1)*pageSize}&ordering=-fecha_tasa`;
    if (filtros.moneda_origen) url += `&id_moneda_origen=${filtros.moneda_origen}`;
    if (filtros.moneda_destino) url += `&id_moneda_destino=${filtros.moneda_destino}`;
    if (filtros.fecha) url += `&fecha_tasa=${filtros.fecha}`;
    get(url)
      .then(res => {
        const data = res as TasaCambioApiResponse;
        if (Array.isArray(data)) {
          setTasas(data);
          setCount(data.length);
        } else {
          setTasas(data.results);
          setCount(data.count);
        }
      })
      .catch(() => setError('Error al cargar tasas de cambio'))
      .finally(() => setLoading(false));
  }, [id_empresa, filtros, page, pageSize]);

  return (
    <PageLayout maxWidth={1100}>
      {/* Tasa oficial BCV global destacada */}
      <div style={{
        background: '#e3f0ff',
        borderRadius: 12,
        padding: 18,
        marginBottom: 24,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 24,
        boxShadow: '0 2px 8px rgba(0,0,0,0.04)'
      }}>
        {loadingTasaOficial ? (
          <span style={{ color: '#888' }}>Cargando tasa oficial BCV...</span>
        ) : tasaOficial ? (
          <>
            <span style={{ fontWeight: 600, color: '#1976d2', fontSize: 18 }}>
              Tasa Oficial BCV USD/VES hoy ({tasaOficial.fecha_tasa}):
            </span>
            <span style={{ fontWeight: 700, color: '#388e3c', fontSize: 22 }}>
              {Number(tasaOficial.valor_tasa).toLocaleString('es-VE', { minimumFractionDigits: 4 })}
            </span>
          </>
        ) : (
          <span style={{ color: '#d32f2f', fontWeight: 500 }}>{errorTasaOficial}</span>
        )}
      </div>
      {/* Encabezado centrado y botón principal */}
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Tasas de Cambio</h2>
      <div style={{ display: 'flex', alignItems: 'center', marginBottom: 24, gap: 16, justifyContent: 'flex-end' }}>
        <Button variant="contained" onClick={() => navigate(`/empresas/${id_empresa}/tasas-cambio/new`)}>
          + Nueva tasa de cambio
        </Button>
      </div>
      {/* Filtros */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12, marginBottom: 18 }}>
        <select
          value={filtros.moneda_origen}
          onChange={e => setFiltros(f => ({ ...f, moneda_origen: e.target.value }))}
          style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', minWidth: 140, fontSize: '1rem', background: '#f6fafd' }}
        >
          <option value="">Moneda Origen</option>
          {monedas.map(m => (
            <option key={m.id_moneda} value={m.id_moneda}>
              {m.nombre} ({m.codigo_iso})
            </option>
          ))}
        </select>
        <select
          value={filtros.moneda_destino}
          onChange={e => setFiltros(f => ({ ...f, moneda_destino: e.target.value }))}
          style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', minWidth: 140, fontSize: '1rem', background: '#f6fafd' }}
        >
          <option value="">Moneda Destino</option>
          {monedas.map(m => (
            <option key={m.id_moneda} value={m.id_moneda}>
              {m.nombre} ({m.codigo_iso})
            </option>
          ))}
        </select>
        <input
          type="date"
          value={filtros.fecha}
          onChange={e => setFiltros(f => ({ ...f, fecha: e.target.value }))}
          style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', minWidth: 140, fontSize: '1rem', background: '#f6fafd' }}
        />
        <Button variant="contained" color="secondary" onClick={() => setFiltros({ moneda_origen: '', moneda_destino: '', fecha: '' })}>
          Limpiar
        </Button>
      </div>
      {loading ? (
        <div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div>
      ) : error ? (
        <div style={{ textAlign: 'center', color: '#d32f2f', padding: 32, fontWeight: 500 }}>{error}</div>
      ) : (
        <div style={{ overflowX: 'auto' }}>
          <table style={{ width: '100%', borderCollapse: 'collapse', background: '#f6fafd', borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
            <thead>
              <tr style={{ background: '#e3f0ff' }}>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Fecha</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Moneda Origen</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Moneda Destino</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Tipo Tasa</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Valor</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Usuario</th>
                <th style={{ padding: '12px 8px', color: '#1976d2', fontWeight: 600 }}>Acciones</th>
              </tr>
            </thead>
            <tbody>
              {tasas.length === 0 ? (
                <tr>
                  <td colSpan={7} style={{ textAlign: 'center', padding: 32, color: '#888' }}>No hay tasas registradas.</td>
                </tr>
              ) : tasas.map(tc => (
                <tr key={tc.id_tasa_cambio} style={{ background: '#fff', borderBottom: '1px solid #e3f0ff' }}>
                  <td style={{ padding: '10px 8px' }}>{tc.fecha_tasa}</td>
                  <td style={{ padding: '10px 8px' }}>{tc.moneda_origen_nombre || tc.id_moneda_origen__codigo_iso || tc.id_moneda_origen}</td>
                  <td style={{ padding: '10px 8px' }}>{tc.moneda_destino_nombre || tc.id_moneda_destino__codigo_iso || tc.id_moneda_destino}</td>
                  <td style={{ padding: '10px 8px' }}>{tc.tipo_tasa}</td>
                  <td style={{ padding: '10px 8px' }}>{tc.valor_tasa}</td>
                  <td style={{ padding: '10px 8px' }}>{tc.usuario_registro_username || tc.id_usuario_registro__username || ''}</td>
                  <td style={{ padding: '10px 8px' }}>
                    <Button variant="contained" onClick={() => navigate(`/tasas-cambio/${tc.id_tasa_cambio}`)}>Ver / Editar</Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {/* Paginación real */}
      <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', marginTop: 24, gap: 8 }}>
        <Button variant="contained" color="secondary" onClick={() => setPage(p => Math.max(1, p - 1))} disabled={page === 1}>Anterior</Button>
        <span style={{ fontWeight: 500 }}>Página {page} de {Math.max(1, Math.ceil(count / pageSize))}</span>
        <Button variant="contained" color="secondary" onClick={() => setPage(p => (p < Math.ceil(count / pageSize) ? p + 1 : p))} disabled={page >= Math.ceil(count / pageSize)}>Siguiente</Button>
        <span style={{ marginLeft: 16 }}>
          <label style={{ fontWeight: 500 }}>Tamaño:
            <select value={pageSize} onChange={e => { setPageSize(Number(e.target.value)); setPage(1); }} style={{ marginLeft: 4, padding: 6, borderRadius: 6, border: '1px solid #cfd8dc' }}>
              {[10, 20, 50, 100].map(sz => <option key={sz} value={sz}>{sz}</option>)}
            </select>
          </label>
        </span>
      </div>
    </PageLayout>
  );
};

export default TasaCambioListPage;
