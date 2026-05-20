import React, { useState, useEffect } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, put } from '../../../services/api';
import { toList } from '../../../utils/api';
import PageLayout from '../../../components/PageLayout';

interface Empresa {
  id_empresa: string;
  nombre_legal: string;
  nombre_comercial: string;
  identificador_fiscal: string;
  email_contacto: string;
  activo: boolean;
  fecha_registro: string;
  id_moneda_base: string;
}

interface Moneda {
  id_moneda: string;
  nombre: string;
  codigo_iso: string;
}

type MonedaApiResponse = Moneda[] | { results: Moneda[] };

const CompanyDetailPage: React.FC = () => {
  const { id_empresa } = useParams<{ id_empresa: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const cleanId = id_empresa?.replace(':', '') || '';

  const [localEmpresa, setLocalEmpresa] = useState<Empresa | null>(null);

  const { data: empresaData, isLoading: loadingEmpresa } = useQuery<Empresa>({
    queryKey: ['/core/empresas/', cleanId],
    queryFn: () => get<Empresa>(`/core/empresas/${cleanId}/`),
    enabled: !!cleanId,
  });

  useEffect(() => {
    if (empresaData) {
      setLocalEmpresa({
        ...empresaData,
        activo: Boolean(empresaData.activo),
        id_moneda_base: empresaData.id_moneda_base ?? '',
      });
    }
  }, [empresaData]);

  const { data: monedas = [] } = useQuery<MonedaApiResponse, Error, Moneda[]>({
    queryKey: ['/finanzas/monedas/activas/'],
    queryFn: () => get<MonedaApiResponse>('/finanzas/monedas/activas/'),
    select: toList,
  });

  const updateMutation = useMutation({
    mutationFn: (data: Empresa) => put<Empresa>(`/core/empresas/${cleanId}/`, { ...data, activo: !!data.activo }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/core/empresas/', cleanId] });
      queryClient.invalidateQueries({ queryKey: ['/core/empresas/'] });
      alert('Empresa actualizada');
    },
    onError: () => alert('Error al actualizar'),
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    if (!localEmpresa) return;
    const { name, value } = e.target;
    if (name === 'activo') {
      setLocalEmpresa({ ...localEmpresa, activo: value === 'true' });
    } else if (name === 'id_moneda_base') {
      setLocalEmpresa({ ...localEmpresa, id_moneda_base: value.toString() });
    } else {
      setLocalEmpresa({ ...localEmpresa, [name]: value });
    }
  };

  const handleSave = () => {
    if (!localEmpresa) return;
    updateMutation.mutate(localEmpresa);
  };

  if (loadingEmpresa || !localEmpresa) return <PageLayout><div style={{ textAlign: 'center', color: '#888', padding: 32 }}>Cargando...</div></PageLayout>;

  return (
    <PageLayout maxWidth={480}>
      <h2 style={{ marginBottom: 24, color: '#1a237e', fontWeight: 700, fontSize: 26, textAlign: 'center' }}>Detalle de empresa</h2>
      {(!monedas || monedas.length === 0) && (
        <div style={{ color: '#d32f2f', fontSize: 13, marginBottom: 12, textAlign: 'center' }}>
          No se encontraron monedas disponibles.
        </div>
      )}
      <form style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Nombre legal
          <input name="nombre_legal" value={localEmpresa.nombre_legal} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Nombre comercial
          <input name="nombre_comercial" value={localEmpresa.nombre_comercial} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Identificador fiscal
          <input name="identificador_fiscal" value={localEmpresa.identificador_fiscal} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Email contacto
          <input name="email_contacto" value={localEmpresa.email_contacto} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }} />
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Activo
          <select name="activo" value={localEmpresa.activo ? 'true' : 'false'} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }}>
            <option value="true">Sí</option>
            <option value="false">No</option>
          </select>
        </label>
        <label style={{ fontWeight: 500, color: '#333', marginBottom: 2 }}>Moneda base
          <select name="id_moneda_base" value={localEmpresa.id_moneda_base?.toString() ?? ''} onChange={handleChange} style={{ width: '100%', padding: '8px 10px', borderRadius: 6, border: '1px solid #cfd8dc', marginTop: 4, fontSize: 15 }}>
            <option value="">Seleccione moneda</option>
            {(Array.isArray(monedas) ? monedas : []).map(moneda => (
              <option key={moneda.id_moneda} value={moneda.id_moneda}>
                {moneda.nombre} ({moneda.codigo_iso})
              </option>
            ))}
          </select>
        </label>
        <button type="button" onClick={handleSave} disabled={updateMutation.isPending} style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 0', fontWeight: 600, fontSize: 16, marginTop: 10, cursor: 'pointer', boxShadow: '0 2px 8px rgba(25,118,210,0.08)' }}>Guardar cambios</button>
      </form>
      <div style={{ marginTop: 28, textAlign: 'center' }}>
        <button onClick={() => navigate('/empresas')} style={{ background: '#e3eafc', color: '#1976d2', border: 'none', borderRadius: 6, padding: '8px 24px', fontWeight: 500, fontSize: 15, cursor: 'pointer' }}>Volver a la lista</button>
      </div>
    </PageLayout>
  );
};

export default CompanyDetailPage;
