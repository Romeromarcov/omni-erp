import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { getTransaccionesFinancieras, exportTransaccionesFinancieras } from '../../../services/transaccionFinancieraService';
import PageLayout from '../../../components/PageLayout';
import { Button, TextField } from '@mui/material';

const tipoTransaccionOptions = [
  { value: '', label: 'Todos' },
  { value: 'ingreso', label: 'Ingreso' },
  { value: 'egreso', label: 'Egreso' },
];

type TransaccionFinanciera = {
  id: string;
  fecha_hora_transaccion: string;
  tipo_transaccion: string;
  monto_transaccion: number;
  id_moneda_transaccion__codigo_iso: string;
  id_moneda_base__codigo_iso?: string;
  monto_base_empresa: number;
  id_moneda_pais_empresa__codigo_iso?: string;
  monto_moneda_pais?: number;
  id_metodo_pago__nombre_metodo: string;
  referencia_pago: string;
  descripcion: string;
  id_usuario_registro__username: string;
  empresa_id?: string;
  estado?: string;
  observaciones?: string;
};

const TransaccionFinancieraListPage: React.FC = () => {
  const { id_empresa } = useParams();
  const navigate = useNavigate();
  const [data, setData] = useState<TransaccionFinanciera[]>([]);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState({ tipo: '', moneda: '', metodo: '', usuario: '', fecha_inicio: '', fecha_fin: '' });

  const empresaIdToUse = id_empresa;

  // Type guard para paginación
  function isPaginated(data: unknown): data is { results: TransaccionFinanciera[] } {
    return !!data && typeof data === 'object' && Array.isArray((data as { results?: unknown }).results);
  }
  useEffect(() => {
    setLoading(true);
    getTransaccionesFinancieras(empresaIdToUse, filters).then(result => {
      if (Array.isArray(result)) {
        setData(result);
      } else if (isPaginated(result)) {
        setData(result.results);
      } else {
        setData([]);
      }
    }).catch(error => {
      console.error('Error fetching transacciones:', error);
      setData([]);
    }).finally(() => {
      setLoading(false);
    });
  }, [empresaIdToUse, filters]);

  if (!empresaIdToUse) {
    return (
      <PageLayout>
        <div style={{ textAlign: 'center', marginTop: 50 }}>
          <h2>Empresa no especificada</h2>
          <p>Por favor, selecciona una empresa para ver las transacciones financieras.</p>
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout maxWidth={1400}>
      <h2 style={{ marginBottom: 16 }}>Transacciones Financieras</h2>
      {loading && <div style={{ marginBottom: 16, textAlign: 'center', color: '#666' }}>Cargando transacciones...</div>}
      <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <select
          value={filters.tipo}
          onChange={(e: React.ChangeEvent<HTMLSelectElement>) => setFilters(f => ({ ...f, tipo: e.target.value }))}
          style={{ padding: 8, borderRadius: 6, border: '1px solid #ccc' }}
        >
          {tipoTransaccionOptions.map(opt => (
            <option key={opt.value} value={opt.value}>{opt.label}</option>
          ))}
        </select>
        <TextField fullWidth placeholder="Moneda" value={filters.moneda} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFilters(f => ({ ...f, moneda: e.target.value }))} />
        <TextField fullWidth placeholder="Método de Pago" value={filters.metodo} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFilters(f => ({ ...f, metodo: e.target.value }))} />
        <TextField fullWidth placeholder="Usuario" value={filters.usuario} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFilters(f => ({ ...f, usuario: e.target.value }))} />
        <TextField fullWidth type="date" label="Desde" value={filters.fecha_inicio} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFilters(f => ({ ...f, fecha_inicio: e.target.value }))} />
        <TextField fullWidth type="date" label="Hasta" value={filters.fecha_fin} onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFilters(f => ({ ...f, fecha_fin: e.target.value }))} />
        <Button variant="contained" onClick={() => navigate(`/empresas/${id_empresa}/transacciones-financieras/new`)}>Nueva Transacción</Button>
        <Button variant="outlined" onClick={() => exportTransaccionesFinancieras(id_empresa, filters)}>Exportar</Button>
      </div>
      <div style={{ overflowX: 'auto', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.1)' }}>
        <table style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: '14px',
          backgroundColor: '#fff'
        }}>
          <thead style={{ backgroundColor: '#f5f5f5' }}>
            <tr>
              <th style={{ padding: '12px 8px', textAlign: 'center', fontWeight: 'bold', borderBottom: '2px solid #e0e0e0' }}>Fecha</th>
              <th style={{ padding: '12px 8px', textAlign: 'center', fontWeight: 'bold', borderBottom: '2px solid #e0e0e0' }}>Tipo</th>
              <th style={{ padding: '12px 8px', textAlign: 'center', fontWeight: 'bold', borderBottom: '2px solid #e0e0e0' }}>Monto</th>
              <th style={{ padding: '12px 8px', textAlign: 'center', fontWeight: 'bold', borderBottom: '2px solid #e0e0e0' }}>Moneda</th>
              <th style={{ padding: '12px 8px', textAlign: 'center', fontWeight: 'bold', borderBottom: '2px solid #e0e0e0' }}>Moneda Base</th>
              <th>Monto Base</th>
              <th>Moneda País</th>
              <th>Monto País</th>
              <th>Método de Pago</th>
              <th>Referencia</th>
              <th>Descripción</th>
              <th>Usuario</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {data.map((row, idx) => {
              return (
                <tr key={row.id || idx} style={{
                  borderBottom: '1px solid #e0e0e0'
                }}>
                  <td style={{ padding: '12px 8px', textAlign: 'center' }}>{row.fecha_hora_transaccion}</td>
                  <td style={{ padding: '12px 8px', textAlign: 'center' }}>{row.tipo_transaccion}</td>
                  <td style={{ padding: '12px 8px', textAlign: 'right', fontWeight: 'bold' }}>{row.monto_transaccion}</td>
                  <td style={{ padding: '12px 8px', textAlign: 'center' }}>{row.id_moneda_transaccion__codigo_iso}</td>
                  <td style={{ padding: '12px 8px', textAlign: 'center' }}>{row.id_moneda_base__codigo_iso || '-'}</td>
                  <td style={{ padding: '12px 8px', textAlign: 'right' }}>{row.monto_base_empresa}</td>
                  <td>{row.id_moneda_pais_empresa__codigo_iso || '-'}</td>
                  <td>{row.monto_moneda_pais !== undefined ? row.monto_moneda_pais : '-'}</td>
                  <td>{row.id_metodo_pago__nombre_metodo}</td>
                  <td>{row.referencia_pago}</td>
                  <td>{row.descripcion}</td>
                  <td>{row.id_usuario_registro__username}</td>
                  <td>
                    <Button variant="outlined" onClick={() => navigate(`/transacciones-financieras/${row.id}`)}>
                      Ver Detalle
                    </Button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
        {data.length === 0 && !loading && (
          <div style={{ textAlign: 'center', padding: 20, color: '#666' }}>
            No se encontraron transacciones financieras.
          </div>
        )}
      </div>
    </PageLayout>
  );
};

export default TransaccionFinancieraListPage;
