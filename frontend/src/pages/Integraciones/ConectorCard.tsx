import React from 'react';
import { useNavigate } from 'react-router-dom';
import type { ConectorInstancia } from '../../services/integrationHubService';

interface Props {
  conector: ConectorInstancia;
}

const ESTADO_COLORS: Record<string, { bg: string; text: string; label: string }> = {
  activo:       { bg: '#e6f4ea', text: '#1e7e34', label: 'Activo' },
  configurando: { bg: '#fff3cd', text: '#856404', label: 'Configurando' },
  error:        { bg: '#fde8e8', text: '#b91c1c', label: 'Error' },
  inactivo:     { bg: '#f3f4f6', text: '#6b7280', label: 'Inactivo' },
};

const ConectorCard: React.FC<Props> = ({ conector }) => {
  const navigate = useNavigate();
  const estado = ESTADO_COLORS[conector.estado] ?? ESTADO_COLORS.inactivo;

  const ultimoSync = conector.ultimo_sync
    ? new Date(conector.ultimo_sync).toLocaleString('es-VE', { dateStyle: 'short', timeStyle: 'short' })
    : 'Nunca';

  return (
    <div
      onClick={() => navigate(`/integraciones/conectores/${conector.id_conector}`)}
      style={{
        background: '#fff',
        border: '1px solid #e5e7eb',
        borderRadius: 10,
        padding: '18px 20px',
        cursor: 'pointer',
        transition: 'box-shadow 0.15s',
        display: 'flex',
        flexDirection: 'column',
        gap: 10,
      }}
      onMouseEnter={e => (e.currentTarget.style.boxShadow = '0 4px 16px rgba(0,0,0,0.10)')}
      onMouseLeave={e => (e.currentTarget.style.boxShadow = 'none')}
    >
      {/* Header */}
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 15, color: '#111827' }}>{conector.nombre}</div>
          <div style={{ fontSize: 12, color: '#6b7280', marginTop: 2 }}>{conector.proveedor_nombre}</div>
        </div>
        <span
          style={{
            padding: '3px 10px',
            borderRadius: 20,
            fontSize: 12,
            fontWeight: 600,
            background: estado.bg,
            color: estado.text,
            whiteSpace: 'nowrap',
          }}
        >
          {estado.label}
        </span>
      </div>

      {/* Host */}
      {conector.configuracion_publica?.host && (
        <div style={{ fontSize: 12, color: '#374151', fontFamily: 'monospace', background: '#f9fafb', padding: '4px 8px', borderRadius: 4 }}>
          {conector.configuracion_publica.host}
        </div>
      )}

      {/* Entidades */}
      {conector.entidades_activas.length > 0 && (
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {conector.entidades_activas.map(e => (
            <span
              key={e}
              style={{
                background: '#eff6ff',
                color: '#1d4ed8',
                borderRadius: 4,
                padding: '2px 6px',
                fontSize: 11,
                fontWeight: 500,
              }}
            >
              {e}
            </span>
          ))}
        </div>
      )}

      {/* Footer */}
      <div style={{ fontSize: 11, color: '#9ca3af', marginTop: 2 }}>
        Último sync: <span style={{ color: '#6b7280' }}>{ultimoSync}</span>
        {conector.version_detectada && (
          <span style={{ marginLeft: 12 }}>v{conector.version_detectada}</span>
        )}
      </div>
    </div>
  );
};

export default ConectorCard;
