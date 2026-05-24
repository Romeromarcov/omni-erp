/**
 * SugerenciasWidget — Dashboard widget de sugerencias de agentes IA.
 *
 * Muestra tarjetas con sugerencias activas (resultado_humano="pendiente")
 * generadas por CobranzaEstrategaAgent y ReordenSugeridorAgent.
 * El usuario puede Aceptar o Rechazar cada sugerencia.
 */
import React, { useCallback, useEffect, useState } from 'react';
import { fetcher } from '../services/api';
import { useNavigate } from 'react-router-dom';
import {
  Alert,
  Box,
  Button,
  Card,
  CardActions,
  CardContent,
  Chip,
  CircularProgress,
  Typography,
} from '@mui/material';

// ── Tipos ─────────────────────────────────────────────────────────────────────

interface Sugerencia {
  id: string;
  agente: string;
  titulo: string;
  descripcion: string;
  categoria: string;
  confianza: number;
  monto: string | null;
  metadata: Record<string, unknown>;
  url_accion: string;
  fecha: string;
}

interface SugerenciasResponse {
  sugerencias: Sugerencia[];
  total: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

const AGENTE_LABEL: Record<string, string> = {
  cobranza_estratega: 'Cobranza',
  reorden_sugeridor: 'Inventario',
  clasificador_gastos: 'Gastos',
  personalizacion_capa2: 'Personalización',
};

const AGENTE_COLOR: Record<string, 'primary' | 'warning' | 'success' | 'info'> = {
  cobranza_estratega: 'warning',
  reorden_sugeridor: 'info',
  clasificador_gastos: 'success',
  personalizacion_capa2: 'primary',
};

function formatConfianza(c: number): string {
  return `${Math.round(c * 100)}%`;
}

// ── Componente ────────────────────────────────────────────────────────────────

const SugerenciasWidget: React.FC = () => {
  const [sugerencias, setSugerencias] = useState<Sugerencia[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [respondiendo, setRespondiendo] = useState<string | null>(null);
  const navigate = useNavigate();

  const cargar = useCallback(async () => {
    try {
      const data = await fetcher<SugerenciasResponse>(
        '/agentes/predicciones/sugerencias-activas/?limite=5'
      );
      setSugerencias(data.sugerencias ?? []);
      setError('');
    } catch {
      setError('No se pudieron cargar las sugerencias.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const responder = async (id: string, accion: 'aceptar' | 'rechazar') => {
    setRespondiendo(id);
    try {
      await fetcher(`/agentes/predicciones/${id}/responder/`, {
        method: 'POST',
        body: JSON.stringify({ accion }),
      });
      setSugerencias((prev) => prev.filter((s) => s.id !== id));
    } catch {
      setError('Error al procesar la sugerencia.');
    } finally {
      setRespondiendo(null);
    }
  };

  if (loading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}>
        <CircularProgress size={28} />
      </Box>
    );
  }

  return (
    <Box>
      <Typography variant="h6" sx={{ mb: 1.5, fontWeight: 600, color: '#1a3a5c' }}>
        🤖 Sugerencias del Asistente IA
      </Typography>

      {error && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {error}
        </Alert>
      )}

      {sugerencias.length === 0 && !error && (
        <Typography variant="body2" color="text.secondary">
          No hay sugerencias pendientes. ¡Todo al día!
        </Typography>
      )}

      <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
        {sugerencias.map((s) => (
          <Card
            key={s.id}
            variant="outlined"
            sx={{
              borderRadius: 2,
              borderColor: '#e0e7ff',
              background: 'linear-gradient(135deg, #f8faff 0%, #ffffff 100%)',
            }}
          >
            <CardContent sx={{ pb: 0.5 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                <Chip
                  label={AGENTE_LABEL[s.agente] ?? s.agente}
                  size="small"
                  color={AGENTE_COLOR[s.agente] ?? 'primary'}
                  sx={{ fontWeight: 600, fontSize: '0.7rem' }}
                />
                <Chip
                  label={`Conf: ${formatConfianza(s.confianza)}`}
                  size="small"
                  variant="outlined"
                  sx={{ fontSize: '0.7rem' }}
                />
                {s.monto && (
                  <Chip
                    label={`$${Number(s.monto).toLocaleString()}`}
                    size="small"
                    variant="outlined"
                    color="warning"
                    sx={{ fontSize: '0.7rem' }}
                  />
                )}
              </Box>
              <Typography variant="subtitle2" sx={{ fontWeight: 600, lineHeight: 1.3 }}>
                {s.titulo}
              </Typography>
              {s.descripcion && s.descripcion !== s.titulo && (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5, fontSize: '0.82rem' }}>
                  {s.descripcion.length > 120 ? `${s.descripcion.slice(0, 120)}…` : s.descripcion}
                </Typography>
              )}
            </CardContent>
            <CardActions sx={{ pt: 0.5, px: 2, pb: 1.5, gap: 1 }}>
              <Button
                size="small"
                variant="contained"
                color="success"
                disabled={respondiendo === s.id}
                onClick={() => responder(s.id, 'aceptar')}
                sx={{ minWidth: 90 }}
              >
                {respondiendo === s.id ? <CircularProgress size={14} /> : '✓ Aceptar'}
              </Button>
              <Button
                size="small"
                variant="outlined"
                color="error"
                disabled={respondiendo === s.id}
                onClick={() => responder(s.id, 'rechazar')}
                sx={{ minWidth: 90 }}
              >
                ✗ Rechazar
              </Button>
              {s.url_accion && (
                <Button
                  size="small"
                  variant="text"
                  color="primary"
                  onClick={() => navigate(s.url_accion)}
                  sx={{ ml: 'auto' }}
                >
                  Ver detalle →
                </Button>
              )}
            </CardActions>
          </Card>
        ))}
      </Box>
    </Box>
  );
};

export default SugerenciasWidget;
