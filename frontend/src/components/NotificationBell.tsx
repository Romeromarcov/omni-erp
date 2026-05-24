import React, { useCallback, useEffect, useRef, useState } from 'react';
import { fetcher } from '../services/api';

interface Notificacion {
  id_notificacion: string;
  tipo: string;
  titulo: string;
  mensaje: string;
  leida: boolean;
  fecha_lectura: string | null;
  url_accion: string;
  fecha_creacion: string;
}

const POLL_INTERVAL_MS = 30_000;

const BELL_ICON = '🔔';

const NotificationBell: React.FC = () => {
  const [notificaciones, setNotificaciones] = useState<Notificacion[]>([]);
  const [open, setOpen] = useState(false);
  const intervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchNoLeidas = useCallback(async () => {
    try {
      const data = await fetcher<Notificacion[]>(
        '/notificaciones/notificaciones/mis-notificaciones/?no_leidas=true'
      );
      setNotificaciones(Array.isArray(data) ? data : []);
    } catch {
      // silencioso si no hay conectividad
    }
  }, []);

  useEffect(() => {
    fetchNoLeidas();
    intervalRef.current = setInterval(fetchNoLeidas, POLL_INTERVAL_MS);
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current);
    };
  }, [fetchNoLeidas]);

  const marcarLeida = async (id: string) => {
    try {
      await fetcher(`/notificaciones/notificaciones/${id}/marcar-leida/`, {
        method: 'PATCH',
        body: JSON.stringify({}),
      });
      setNotificaciones(prev => prev.filter(n => n.id_notificacion !== id));
    } catch {
      // ignorar errores de red
    }
  };

  const count = notificaciones.length;

  return (
    <div style={{ position: 'relative', display: 'inline-block' }}>
      <button
        onClick={() => setOpen(o => !o)}
        aria-label={`Notificaciones${count > 0 ? ` (${count} sin leer)` : ''}`}
        style={{
          background: 'none',
          border: 'none',
          cursor: 'pointer',
          fontSize: 22,
          position: 'relative',
          padding: '4px 8px',
        }}
      >
        {BELL_ICON}
        {count > 0 && (
          <span
            style={{
              position: 'absolute',
              top: 0,
              right: 0,
              background: '#e53935',
              color: '#fff',
              borderRadius: '50%',
              fontSize: 11,
              width: 18,
              height: 18,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              fontWeight: 700,
            }}
          >
            {count > 9 ? '9+' : count}
          </span>
        )}
      </button>

      {open && (
        <div
          style={{
            position: 'absolute',
            right: 0,
            top: '110%',
            width: 320,
            background: '#fff',
            boxShadow: '0 4px 16px rgba(0,0,0,0.15)',
            borderRadius: 8,
            zIndex: 1000,
            maxHeight: 400,
            overflowY: 'auto',
          }}
        >
          <div
            style={{
              padding: '10px 14px',
              borderBottom: '1px solid #f0f0f0',
              fontWeight: 600,
              fontSize: 14,
            }}
          >
            Notificaciones
            {count > 0 && (
              <span style={{ marginLeft: 8, color: '#e53935', fontSize: 12 }}>
                ({count} sin leer)
              </span>
            )}
          </div>

          {notificaciones.length === 0 ? (
            <div style={{ padding: '16px 14px', color: '#888', fontSize: 13 }}>
              Sin notificaciones pendientes
            </div>
          ) : (
            notificaciones.map(n => (
              <div
                key={n.id_notificacion}
                style={{
                  padding: '10px 14px',
                  borderBottom: '1px solid #f8f8f8',
                  background: '#f0f7ff',
                }}
              >
                <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 2 }}>
                  {n.titulo}
                </div>
                <div style={{ fontSize: 12, color: '#555', marginBottom: 6 }}>
                  {n.mensaje}
                </div>
                <div style={{ display: 'flex', gap: 8 }}>
                  {n.url_accion && (
                    <a
                      href={n.url_accion}
                      style={{ fontSize: 11, color: '#1976d2' }}
                      onClick={() => setOpen(false)}
                    >
                      Ver detalle
                    </a>
                  )}
                  <button
                    onClick={() => marcarLeida(n.id_notificacion)}
                    style={{
                      fontSize: 11,
                      color: '#888',
                      background: 'none',
                      border: 'none',
                      cursor: 'pointer',
                      padding: 0,
                    }}
                  >
                    Marcar leída
                  </button>
                </div>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
};

export default NotificationBell;
