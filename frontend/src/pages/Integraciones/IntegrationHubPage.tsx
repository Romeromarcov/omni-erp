import React, { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  getConectores,
  getIntegrationHubStatus,
} from '../../services/integrationHubService';
import ConectorCard from './ConectorCard';
import NuevoConectorModal from './NuevoConectorModal';

const IntegrationHubPage: React.FC = () => {
  const [showModal, setShowModal] = useState(false);

  const { data: conectoresData, isLoading } = useQuery({
    queryKey: ['/integration-hub/instancias/'],
    queryFn: getConectores,
  });

  const { data: status } = useQuery({
    queryKey: ['/integration-hub/status/'],
    queryFn: getIntegrationHubStatus,
    refetchInterval: 30_000,
  });

  const conectores = conectoresData?.results ?? [];

  const stat = (label: string, value: number | string, color = '#111827') => (
    <div
      style={{
        background: '#fff',
        border: '1px solid #e5e7eb',
        borderRadius: 10,
        padding: '16px 22px',
        minWidth: 120,
      }}
    >
      <div style={{ fontSize: 24, fontWeight: 700, color }}>{value}</div>
      <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{label}</div>
    </div>
  );

  return (
    <div style={{ padding: '28px 32px', maxWidth: 1200 }}>
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 24 }}>
        <div>
          <h1 style={{ margin: 0, fontSize: 26, fontWeight: 800, color: '#111827' }}>
            Integration Hub
          </h1>
          <p style={{ margin: '4px 0 0', fontSize: 14, color: '#6b7280' }}>
            Conecta Omni ERP con cualquier sistema externo
          </p>
        </div>
        <button
          onClick={() => setShowModal(true)}
          style={{
            background: '#2563eb',
            color: '#fff',
            border: 'none',
            borderRadius: 8,
            padding: '10px 20px',
            fontWeight: 600,
            fontSize: 14,
            cursor: 'pointer',
          }}
        >
          + Nuevo conector
        </button>
      </div>

      {/* Stats */}
      {status && (
        <div style={{ display: 'flex', gap: 12, marginBottom: 28, flexWrap: 'wrap' }}>
          {stat('Conectores activos', status.conectores_activos, '#2563eb')}
          {stat('Total conectores', status.conectores_total)}
          {stat('Jobs (24h)', status.ultima_24h.total)}
          {stat('Completados', status.ultima_24h.completados, '#16a34a')}
          {status.ultima_24h.fallidos > 0 &&
            stat('Fallidos', status.ultima_24h.fallidos, '#dc2626')}
          {status.ultima_24h.en_progreso > 0 &&
            stat('En progreso', status.ultima_24h.en_progreso, '#d97706')}
        </div>
      )}

      {/* Grid de conectores */}
      {isLoading ? (
        <div style={{ textAlign: 'center', padding: 60, color: '#9ca3af' }}>Cargando conectores…</div>
      ) : conectores.length === 0 ? (
        <div
          style={{
            border: '2px dashed #e5e7eb',
            borderRadius: 12,
            padding: '60px 32px',
            textAlign: 'center',
          }}
        >
          <div style={{ fontSize: 40, marginBottom: 12 }}>🔌</div>
          <div style={{ fontWeight: 700, fontSize: 18, color: '#111827', marginBottom: 6 }}>
            Sin conectores configurados
          </div>
          <div style={{ color: '#6b7280', marginBottom: 20, fontSize: 14 }}>
            Conecta tu primera plataforma externa para empezar a sincronizar datos.
          </div>
          <button
            onClick={() => setShowModal(true)}
            style={{
              background: '#2563eb',
              color: '#fff',
              border: 'none',
              borderRadius: 8,
              padding: '10px 20px',
              fontWeight: 600,
              fontSize: 14,
              cursor: 'pointer',
            }}
          >
            Agregar primer conector
          </button>
        </div>
      ) : (
        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))',
            gap: 16,
          }}
        >
          {conectores.map(c => (
            <ConectorCard key={c.id_conector} conector={c} />
          ))}
        </div>
      )}

      {showModal && <NuevoConectorModal onClose={() => setShowModal(false)} />}
    </div>
  );
};

export default IntegrationHubPage;
