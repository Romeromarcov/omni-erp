import React, { useEffect, useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import PageLayout from '../../../components/PageLayout';
import { getCuentasBancarias } from '../../../services/cuentaBancariaService';
import { Button, TextField } from '@mui/material';

type CuentaBancaria = {
  id_cuenta_bancaria: string;
  nombre_banco: string;
  numero_cuenta: string;
  tipo_cuenta: string;
  moneda_codigo_iso: string;
  saldo_actual: number;
  activo: boolean;
};

const CuentaBancariaListPage: React.FC = () => {
  const { id_empresa } = useParams<{ id_empresa: string }>();
  const navigate = useNavigate();
  const [data, setData] = useState<CuentaBancaria[]>([]);
  const [filters, setFilters] = useState<{ banco: string; moneda: string; activo: string }>({ banco: '', moneda: '', activo: '' });
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!id_empresa) return;
    setLoading(true);
    getCuentasBancarias(id_empresa, filters)
      .then((result) => {
        if (Array.isArray(result)) {
          setData(result as CuentaBancaria[]);
        } else if (result && typeof result === 'object' && 'results' in result && Array.isArray((result as { results: CuentaBancaria[] }).results)) {
          setData((result as { results: CuentaBancaria[] }).results);
        } else {
          setData([]);
        }
      })
      .finally(() => setLoading(false));
  }, [id_empresa, filters]);

  if (!id_empresa) {
    return (
      <PageLayout>
        <h2 style={{ marginBottom: 16 }}>Gestión de Cuentas Bancarias</h2>
        <div style={{ margin: '32px 0', textAlign: 'center', color: '#c00', fontSize: 18 }}>
          Seleccione una empresa para ver sus cuentas bancarias.
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout maxWidth={1200}>
      <h2 style={{ marginBottom: 16 }}>Gestión de Cuentas Bancarias</h2>
      <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <TextField fullWidth placeholder="Banco" value={filters.banco} onChange={e => setFilters(f => ({ ...f, banco: e.target.value }))} />
        <TextField fullWidth placeholder="Moneda" value={filters.moneda} onChange={e => setFilters(f => ({ ...f, moneda: e.target.value }))} />
        <select value={filters.activo} onChange={e => setFilters(f => ({ ...f, activo: e.target.value }))} style={{ padding: 8, borderRadius: 6, border: '1px solid #ccc' }}>
          <option value="">Todos</option>
          <option value="true">Activas</option>
          <option value="false">Inactivas</option>
        </select>
        <Button variant="contained" onClick={() => navigate(`/empresas/${id_empresa}/cuentas-bancarias/new`)}>Nueva Cuenta</Button>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th>Banco</th>
              <th>Número de Cuenta</th>
              <th>Tipo</th>
              <th>Moneda</th>
              <th>Saldo Actual</th>
              <th>Activa</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <tr><td colSpan={7} style={{ textAlign: 'center' }}>Cargando...</td></tr>
            ) : data.length === 0 ? (
              <tr><td colSpan={7} style={{ textAlign: 'center' }}>No hay cuentas bancarias registradas.</td></tr>
            ) : data.map((row) => (
              <tr key={row.id_cuenta_bancaria}>
                <td>{row.nombre_banco}</td>
                <td>{row.numero_cuenta}</td>
                <td>{row.tipo_cuenta}</td>
                <td>{row.moneda_codigo_iso}</td>
                <td>{Number(row.saldo_actual).toFixed(2)}</td>
                <td>{row.activo ? 'Sí' : 'No'}</td>
                <td style={{ display: 'flex', gap: 4 }}>
                  <Button key={`detalle-${row.id_cuenta_bancaria}`} variant="outlined" onClick={() => navigate(`/cuentas-bancarias/${row.id_cuenta_bancaria}`)}>Ver Detalle</Button>
                  <Button key={`movimientos-${row.id_cuenta_bancaria}`} variant="outlined" onClick={() => navigate(`/cuentas-bancarias/${row.id_cuenta_bancaria}/movimientos`)}>
                    Movimientos
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PageLayout>
  );
};

export default CuentaBancariaListPage;
