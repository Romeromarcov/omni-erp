import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { get, put, post } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';
import type { CatalogoValor } from '../../../types/configuracion';
import { Button } from '@mui/material';

const CatalogoValorDetailPage: React.FC = () => {
  const { id_catalogo_valor } = useParams<{ id_catalogo_valor: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState<Partial<CatalogoValor>>({
    codigo_catalogo: '',
    valor: '',
    descripcion: '',
    orden: 0,
    activo: true,
  });

  const isEditing = !!id_catalogo_valor;

  useEffect(() => {
    if (isEditing) {
      get(`/configuracion_motor/catalogos-valor/${id_catalogo_valor}/`)
        .then((data) => setFormData(data as CatalogoValor))
        .catch(() => navigate('/configuracion/catalogos-valor'));
    }
  }, [id_catalogo_valor, isEditing, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      if (isEditing) {
        await put(`/configuracion_motor/catalogos-valor/${id_catalogo_valor}/`, formData);
      } else {
        await post('/configuracion_motor/catalogos-valor/', formData);
      }
      navigate('/configuracion/catalogos-valor');
    } catch (error) {
      console.error('Error saving catalogo valor:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? (e.target as HTMLInputElement).checked : (type === 'number' ? Number(value) : value)
    }));
  };

  return (
    <PageLayout>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>
        {isEditing ? 'Editar Valor de Catálogo' : 'Nuevo Valor de Catálogo'}
      </h2>

      <form onSubmit={handleSubmit} style={{ maxWidth: 600, margin: '0 auto', background: '#f6fafd', padding: 24, borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: '#1976d2' }}>Código del Catálogo *</label>
          <input
            type="text"
            name="codigo_catalogo"
            value={formData.codigo_catalogo || ''}
            onChange={handleChange}
            required
            placeholder="Ej: ESTADO_CIVIL, TIPO_DOCUMENTO, etc."
            style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: '#1976d2' }}>Valor *</label>
          <input
            type="text"
            name="valor"
            value={formData.valor || ''}
            onChange={handleChange}
            required
            placeholder="Ej: SOLTERO, CEDULA, ACTIVO, etc."
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
            placeholder="Descripción opcional del valor"
            style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: '#1976d2' }}>Orden</label>
          <input
            type="number"
            name="orden"
            value={formData.orden || 0}
            onChange={handleChange}
            min="0"
            style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
          />
        </div>

        <div style={{ marginBottom: 24 }}>
          <label style={{ display: 'flex', alignItems: 'center', fontWeight: 600, color: '#1976d2' }}>
            <input
              type="checkbox"
              name="activo"
              checked={formData.activo || false}
              onChange={handleChange}
              style={{ marginRight: 8 }}
            />
            Activo
          </label>
        </div>

        <div style={{ display: 'flex', gap: 16, justifyContent: 'center' }}>
          <Button
            type="button"
            onClick={() => navigate('/configuracion/catalogos-valor')}
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

export default CatalogoValorDetailPage;