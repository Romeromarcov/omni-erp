import React, { useEffect, useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import { get, put, post } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';
import type { ParametroSistema } from '../../../types/configuracion';
import { Button } from '@mui/material';

const ParametroSistemaDetailPage: React.FC = () => {
  const { id_parametro } = useParams<{ id_parametro: string }>();
  const navigate = useNavigate();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState<Partial<ParametroSistema>>({
    nombre_parametro: '',
    codigo_parametro: '',
    valor_parametro: '',
    tipo_dato: 'TEXTO',
    descripcion: '',
    activo: true,
  });

  const isEditing = !!id_parametro;

  useEffect(() => {
    if (isEditing) {
      get(`/configuracion_motor/parametros-sistema/${id_parametro}/`)
        .then((data) => setFormData(data as ParametroSistema))
        .catch(() => navigate('/configuracion/parametros-sistema'));
    }
  }, [id_parametro, isEditing, navigate]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      if (isEditing) {
        await put(`/configuracion_motor/parametros-sistema/${id_parametro}/`, formData);
      } else {
        await post('/configuracion_motor/parametros-sistema/', formData);
      }
      navigate('/configuracion/parametros-sistema');
    } catch (error) {
      console.error('Error saving parametro sistema:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target;
    setFormData(prev => ({
      ...prev,
      [name]: type === 'checkbox' ? (e.target as HTMLInputElement).checked : value
    }));
  };

  return (
    <PageLayout>
      <h2 style={{ textAlign: 'center', color: '#1976d2', marginBottom: 24 }}>
        {isEditing ? 'Editar Parámetro del Sistema' : 'Nuevo Parámetro del Sistema'}
      </h2>

      <form onSubmit={handleSubmit} style={{ maxWidth: 600, margin: '0 auto', background: '#f6fafd', padding: 24, borderRadius: 12, boxShadow: '0 2px 8px rgba(0,0,0,0.04)' }}>
        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: '#1976d2' }}>Código del Parámetro *</label>
          <input
            type="text"
            name="codigo_parametro"
            value={formData.codigo_parametro || ''}
            onChange={handleChange}
            required
            style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: '#1976d2' }}>Nombre del Parámetro *</label>
          <input
            type="text"
            name="nombre_parametro"
            value={formData.nombre_parametro || ''}
            onChange={handleChange}
            required
            style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
          />
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: '#1976d2' }}>Tipo de Dato *</label>
          <select
            name="tipo_dato"
            value={formData.tipo_dato || 'TEXTO'}
            onChange={handleChange}
            required
            style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
          >
            <option value="TEXTO">Texto</option>
            <option value="NUMERO">Número</option>
            <option value="BOOLEANO">Booleano</option>
            <option value="FECHA">Fecha</option>
          </select>
        </div>

        <div style={{ marginBottom: 16 }}>
          <label style={{ display: 'block', marginBottom: 8, fontWeight: 600, color: '#1976d2' }}>Valor del Parámetro *</label>
          {formData.tipo_dato === 'BOOLEANO' ? (
            <select
              name="valor_parametro"
              value={formData.valor_parametro || ''}
              onChange={handleChange}
              required
              style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
            >
              <option value="">Seleccionar...</option>
              <option value="true">Verdadero</option>
              <option value="false">Falso</option>
            </select>
          ) : formData.tipo_dato === 'FECHA' ? (
            <input
              type="date"
              name="valor_parametro"
              value={formData.valor_parametro || ''}
              onChange={handleChange}
              required
              style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
            />
          ) : (
            <input
              type={formData.tipo_dato === 'NUMERO' ? 'number' : 'text'}
              name="valor_parametro"
              value={formData.valor_parametro || ''}
              onChange={handleChange}
              required
              style={{ width: '100%', padding: 10, borderRadius: 8, border: '1px solid #cfd8dc', fontSize: '1rem' }}
            />
          )}
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
            onClick={() => navigate('/configuracion/parametros-sistema')}
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

export default ParametroSistemaDetailPage;