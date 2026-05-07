

import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { get, put } from '../../../services/api';
import { fetchMonedas } from '../../../services/monedas';
import type { Moneda } from '../../../services/monedas';
import { fetchEmpresas } from '../../../services/empresas';
import type { Empresa } from '../../../services/empresas';
import PageLayout from '../../../components/PageLayout';
import { Button } from '@mui/material';

interface TasaCambioDetail {
  id_tasa_cambio: string;
  id_empresa: string;
  id_moneda_origen: string;
  id_moneda_destino: string;
  tipo_tasa: string;
  valor_tasa: string;
  fecha_tasa: string;
  hora_tasa?: string;
  id_usuario_registro__username?: string;
  empresa_nombre?: string;
}

const TasaCambioDetailPage: React.FC = () => {
  const { id_tasa_cambio } = useParams();
  const navigate = useNavigate();
  const [tasa, setTasa] = useState<TasaCambioDetail | null>(null);
  const [edit, setEdit] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [monedas, setMonedas] = useState<Moneda[]>([]);
  const [empresas, setEmpresas] = useState<Empresa[]>([]);

  // Cargar monedas y empresas
  useEffect(() => {
    fetchMonedas().then(setMonedas);
    fetchEmpresas().then(res => {
      // Type guard para paginación
      type PaginatedEmpresas = { results: Empresa[] };
      function isPaginated(data: unknown): data is PaginatedEmpresas {
        return !!data && typeof data === 'object' && Array.isArray((data as PaginatedEmpresas).results);
      }
      if (Array.isArray(res)) setEmpresas(res);
      else if (isPaginated(res)) setEmpresas((res as PaginatedEmpresas).results);
      else setEmpresas([]);
    });
  }, []);

  useEffect(() => {
    get(`/finanzas/tasas-cambio/${id_tasa_cambio}/`)
      .then((data) => setTasa(data as TasaCambioDetail))
      .catch(() => setError('Error al cargar tasa de cambio'))
      .finally(() => setLoading(false));
  }, [id_tasa_cambio]);

  const handleUpdate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!tasa) return;
    setError('');
    setLoading(true);
    try {
      await put(`/finanzas/tasas-cambio/${id_tasa_cambio}/`, tasa as unknown as Record<string, unknown>);
      setEdit(false);
    } catch {
      setError('Error al actualizar tasa de cambio');
    } finally {
      setLoading(false);
    }
  };

  if (loading) return <PageLayout><div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div></PageLayout>;
  if (error) return <PageLayout><div style={{ textAlign: 'center', color: 'red', padding: 32 }}>{error}</div></PageLayout>;
  if (!tasa) return <PageLayout><div style={{ textAlign: 'center', color: '#888', padding: 32 }}>No encontrada</div></PageLayout>;

  // Helpers para mostrar nombres/códigos
  const monedaOrigen = monedas.find(m => m.id_moneda === tasa.id_moneda_origen);
  const monedaDestino = monedas.find(m => m.id_moneda === tasa.id_moneda_destino);
  const empresa = empresas.find(e => e.id_empresa === tasa.id_empresa);

  return (
    <PageLayout maxWidth={500}>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>Detalle de Tasa de Cambio</h2>
      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: 12 }}>
        <Button variant="contained" color="secondary" onClick={() => navigate(-1)}>
          Volver
        </Button>
      </div>
      {!edit ? (
        <div style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div><b>Empresa:</b> {empresa ? (empresa.nombre_comercial || empresa.nombre_legal) : (tasa.empresa_nombre || tasa.id_empresa)}</div>
          <div><b>Moneda Origen:</b> {monedaOrigen ? `${monedaOrigen.nombre} (${monedaOrigen.codigo_iso})` : tasa.id_moneda_origen}</div>
          <div><b>Moneda Destino:</b> {monedaDestino ? `${monedaDestino.nombre} (${monedaDestino.codigo_iso})` : tasa.id_moneda_destino}</div>
          <div><b>Tipo Tasa:</b> {tasa.tipo_tasa}</div>
          <div><b>Valor:</b> {tasa.valor_tasa}</div>
          <div><b>Fecha:</b> {tasa.fecha_tasa}</div>
          <div><b>Hora:</b> {tasa.hora_tasa || '-'}</div>
          <div><b>Usuario:</b> {tasa.id_usuario_registro__username || '-'}</div>
          <Button variant="contained" onClick={() => setEdit(true)} style={{ marginTop: 8, alignSelf: 'flex-end' }}>Editar</Button>
        </div>
      ) : (
        <form onSubmit={handleUpdate} style={{ marginTop: 8, display: 'flex', flexDirection: 'column', gap: 14 }}>
          <div><b>Empresa:</b> {empresa ? (empresa.nombre_comercial || empresa.nombre_legal) : (tasa.empresa_nombre || tasa.id_empresa)}</div>
          <label style={{ fontWeight: 500 }}>Moneda Origen
            <select value={tasa.id_moneda_origen} onChange={e => setTasa({ ...tasa, id_moneda_origen: e.target.value })} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }}>
              <option value="">Seleccione moneda</option>
              {monedas.map(m => (
                <option key={m.id_moneda} value={m.id_moneda}>{m.nombre} ({m.codigo_iso})</option>
              ))}
            </select>
          </label>
          <label style={{ fontWeight: 500 }}>Moneda Destino
            <select value={tasa.id_moneda_destino} onChange={e => setTasa({ ...tasa, id_moneda_destino: e.target.value })} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }}>
              <option value="">Seleccione moneda</option>
              {monedas.map(m => (
                <option key={m.id_moneda} value={m.id_moneda}>{m.nombre} ({m.codigo_iso})</option>
              ))}
            </select>
          </label>
          <label style={{ fontWeight: 500 }}>Tipo Tasa
            <select value={tasa.tipo_tasa} onChange={e => setTasa({ ...tasa, tipo_tasa: e.target.value })} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }}>
              <option value="">Seleccione tipo</option>
              <option value="OFICIAL_BCV">Oficial BCV</option>
              <option value="ESPECIAL_USUARIO">Especial Usuario</option>
              <option value="PROMEDIO_MERCADO">Promedio Mercado</option>
              <option value="FIJA">Fija</option>
            </select>
          </label>
          <label style={{ fontWeight: 500 }}>Valor
            <input value={tasa.valor_tasa} onChange={e => setTasa({ ...tasa, valor_tasa: e.target.value })} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }} />
          </label>
          <label style={{ fontWeight: 500 }}>Fecha
            <input type="date" value={tasa.fecha_tasa} onChange={e => setTasa({ ...tasa, fecha_tasa: e.target.value })} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }} />
          </label>
          <label style={{ fontWeight: 500 }}>Hora
            <input type="time" value={tasa.hora_tasa || ''} onChange={e => setTasa({ ...tasa, hora_tasa: e.target.value })} style={{ padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', background: '#f6fafd', marginTop: 4 }} />
          </label>
          <div><b>Usuario:</b> {tasa.id_usuario_registro__username || '-'}</div>
          {error && <div style={{ color: 'red', marginTop: 8 }}>{error}</div>}
          <div style={{ display: 'flex', gap: 12, marginTop: 8, justifyContent: 'flex-end' }}>
            <Button type="submit" variant="contained" disabled={loading}>{loading ? 'Actualizando...' : 'Actualizar'}</Button>
            <Button type="button" variant="contained" color="secondary" onClick={() => setEdit(false)}>Cancelar</Button>
          </div>
        </form>
      )}
    </PageLayout>
  );
};

export default TasaCambioDetailPage;
