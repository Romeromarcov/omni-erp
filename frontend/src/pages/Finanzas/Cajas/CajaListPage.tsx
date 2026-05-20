import React, { useState } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import PageLayout from '../../../components/PageLayout';
import { useQuery } from '@tanstack/react-query';
import { getCajas } from '../../../services/cajaService';
import { toList } from '../../../utils/api';
import { Button, TextField } from '@mui/material';

type Caja = {
  id_caja: string;
  nombre: string;
  sucursal_nombre: string;
  moneda_codigo_iso: string;
  saldo_actual: number;
  activa: boolean;
  tipo_caja: string;
  tipo_caja_display?: string;
};

type CajaApiResponse = Caja[] | { results: Caja[] };

const CajaListPage: React.FC = () => {
  const { id_empresa } = useParams<{ id_empresa: string }>();
  const navigate = useNavigate();
  const [filters, setFilters] = useState<{ sucursal: string; moneda: string; activo: string }>({ sucursal: '', moneda: '', activo: '' });

  const { data: data = [], isLoading } = useQuery<CajaApiResponse, Error, Caja[]>({
    queryKey: ['/finanzas/cajas/', id_empresa, filters],
    queryFn: () => getCajas(id_empresa!, filters) as Promise<CajaApiResponse>,
    select: toList,
    enabled: !!id_empresa,
  });

  if (!id_empresa) {
    return (
      <PageLayout>
        <h2 style={{ marginBottom: 16 }}>Gestión de Cajas</h2>
        <div style={{ margin: '32px 0', textAlign: 'center', color: '#c00', fontSize: 18 }}>
          Seleccione una empresa para ver sus cajas.
        </div>
      </PageLayout>
    );
  }

  return (
    <PageLayout maxWidth={1200}>
      <h2 style={{ marginBottom: 16 }}>Gestión de Cajas</h2>
      <div style={{ marginBottom: 16, display: 'flex', gap: 8, flexWrap: 'wrap' }}>
        <TextField fullWidth placeholder="Sucursal" value={filters.sucursal} onChange={e => setFilters(f => ({ ...f, sucursal: e.target.value }))} />
        <TextField fullWidth placeholder="Moneda" value={filters.moneda} onChange={e => setFilters(f => ({ ...f, moneda: e.target.value }))} />
        <select value={filters.activo} onChange={e => setFilters(f => ({ ...f, activo: e.target.value }))} style={{ padding: 8, borderRadius: 6, border: '1px solid #ccc' }}>
          <option value="">Todos</option>
          <option value="true">Activos</option>
          <option value="false">Inactivos</option>
        </select>
        <Button variant="contained" onClick={() => navigate(`/empresas/${id_empresa}/cajas/new`)}>Nueva Caja</Button>
      </div>
      <div style={{ overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse' }}>
          <thead>
            <tr>
              <th>Nombre Caja</th>
              <th>Tipo</th>
              <th>Sucursal</th>
              <th>Moneda</th>
              <th>Saldo Actual</th>
              <th>Activo</th>
              <th>Acciones</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={6} style={{ textAlign: 'center' }}>Cargando...</td></tr>
            ) : data.length === 0 ? (
              <tr><td colSpan={6} style={{ textAlign: 'center' }}>No hay cajas registradas.</td></tr>
            ) : data.map((row) => (
              <tr key={row.id_caja}>
                <td>{row.nombre}</td>
                <td>{row.tipo_caja_display || row.tipo_caja}</td>
                <td>{row.sucursal_nombre}</td>
                <td>{row.moneda_codigo_iso}</td>
                <td>{Number(row.saldo_actual).toFixed(2)}</td>
                <td>{row.activa ? 'Sí' : 'No'}</td>
                <td style={{ display: 'flex', gap: 4 }}>
                  <Button key={`detalle-${row.id_caja}`} variant="outlined" onClick={() => navigate(`/cajas/${row.id_caja}`)}>Ver Detalle</Button>
                  <Button key={`movimientos-${row.id_caja}`} variant="outlined" onClick={() => navigate(`/cajas/${row.id_caja}/movimientos-caja-banco`)}>Movimientos</Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </PageLayout>
  );
};

export default CajaListPage;
