import React, { useState, useEffect } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { get, put, post } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';
import type { TipoDocumento } from '../../../types/configuracion';
import { Button } from '@mui/material';

const TipoDocumentoDetailPage: React.FC = () => {
  const { id_tipo_documento } = useParams<{ id_tipo_documento: string }>();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [formData, setFormData] = useState<Partial<TipoDocumento>>({
    codigo: '',
    nombre: '',
    descripcion: '',
    modulo_origen: '',
    es_transaccional: true,
    prefijo_correlativo: '',
    ultimo_correlativo: 0,
  });

  const isEditing = !!id_tipo_documento;

  const { data: existingData } = useQuery<TipoDocumento>({
    queryKey: ['/configuracion_motor/tipos-documento/', id_tipo_documento],
    queryFn: () => get<TipoDocumento>(`/configuracion_motor/tipos-documento/${id_tipo_documento}/`),
    enabled: isEditing,
  });

  useEffect(() => {
    if (existingData) {
      setFormData(existingData);
    }
  }, [existingData]);

  const saveMutation = useMutation({
    mutationFn: (data: Partial<TipoDocumento>) => {
      if (isEditing) {
        return put<TipoDocumento>(`/configuracion_motor/tipos-documento/${id_tipo_documento}/`, data as Record<string, unknown>);
      }
      return post<TipoDocumento>('/configuracion_motor/tipos-documento/', data as Record<string, unknown>);
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/configuracion_motor/tipos-documento/'] });
      navigate('/configuracion/tipos-documento');
    },
    onError: (error) => {
      console.error('Error saving tipo documento:', error);
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    saveMutation.mutate(formData);
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? (e.target as HTMLInputElement).checked : value
    }));
  };

  const loading = saveMutation.isPending;

  return (
    <PageLayout>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>
        {isEditing ? 'Editar Tipo de Documento' : 'Nuevo Tipo de Documento'}
      </h2>

      <form onSubmit={handleSubmit} style={{ maxWidth: 600, margin: '0 auto', background: '#f6fafd', padding: 24, borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: '#1976d2' }}>Código *</label>
          <input
            type="text"
            name="codigo"
            value={formData.codigo || ''}
            onChange={handleChange}
            required
            style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: '#1976d2' }}>Nombre *</label>
          <input
            type="text"
            name="nombre"
            value={formData.nombre || ''}
            onChange={handleChange}
            required
            style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: '#1976d2' }}>Descripción</label>
          <textarea
            name="descripcion"
            value={formData.descripcion || ''}
            onChange={handleChange}
            rows={3}
            style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: '#1976d2' }}>Módulo Origen *</label>
          <select
            name="modulo_origen"
            value={formData.modulo_origen || ''}
            onChange={handleChange}
            required
            style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
          >
            <option value="">Seleccionar módulo...</option>
            <option value="VENTAS">Ventas</option>
            <option value="COMPRAS">Compras</option>
            <option value="INVENTARIO">Inventario</option>
            <option value="FINANZAS">Finanzas</option>
            <option value="NOMINA">Nómina</option>
            <option value="CONTABILIDAD">Contabilidad</option>
          </select>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'flex', alignItems: 'center', fontWeight: 600, color: '#1976d2' }}>
            <input
              type="checkbox"
              name="es_transaccional"
              checked={formData.es_transaccional || false}
              onChange={handleChange}
              style={{ marginRight: 8 }}
            />
            Es transaccional
          </label>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: '#1976d2' }}>Prefijo Correlativo</label>
          <input
            type="text"
            name="prefijo_correlativo"
            value={formData.prefijo_correlativo || ''}
            onChange={handleChange}
            style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
          />
        </div>

        <div style={{ marginBottom: 24 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: '#1976d2' }}>Último Correlativo</label>
          <input
            type="number"
            name="ultimo_correlativo"
            value={formData.ultimo_correlativo || 0}
            onChange={handleChange}
            min="0"
            style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
          />
        </div>

        <div style={{ display: 'flex', gap: 16, justifyContent: 'center' }}>
          <Button
            type="button"
            onClick={() => navigate('/configuracion/tipos-documento')}
            style={{ background: '#f5f5f5', color: '#666', border: '1px solid #ddd', borderRadius: 6, padding: '10px 24px', fontWeight: 500, cursor: 'pointer' }}
          >
            Cancelar
          </Button>
          <Button
            type="submit"
            disabled={loading}
            style={{ background: '#1976d2', color: '#fff', border: 'none', borderRadius: 6, padding: '10px 24px', fontWeight: 500, cursor: loading ? 'not-allowed' : 'pointer', opacity: loading ? 0.7 : 1 }}
          >
            {loading ? 'Guardando...' : (isEditing ? 'Actualizar' : 'Crear')}
          </Button>
        </div>
      </form>
    </PageLayout>
  );
};

export default TipoDocumentoDetailPage;
