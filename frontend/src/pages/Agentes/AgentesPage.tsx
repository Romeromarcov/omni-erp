import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  Divider,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import AutoAwesomeOutlined from '@mui/icons-material/AutoAwesomeOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  prediccionesService,
  AGENTES,
  RESULTADOS_HUMANOS,
  type Agente,
  type ResultadoHumano,
  type PrediccionAgente,
} from '../../services/agentesService';
import { agentesKeys } from '../../lib/queryKeys';
import { mensajeDeError } from '../../utils/api';

// ── Etiquetas y colores ─────────────────────────────────────────────────────

const AGENTE_LABEL = new Map<string, string>([
  ['clasificador_gastos', 'Clasificador de Gastos'],
  ['cobranza_estratega', 'Estratega de Cobranza'],
  ['reorden_sugeridor', 'Sugeridor de Reorden'],
  ['personalizacion_capa2', 'Personalización Capa 2'],
]);

const RESULTADO_LABEL = new Map<string, string>([
  ['pendiente', 'Pendiente'],
  ['aceptada', 'Aceptada'],
  ['rechazada', 'Rechazada'],
]);

const labelAgente = (a: string): string => AGENTE_LABEL.get(a) ?? a;
const labelResultado = (r: string): string => RESULTADO_LABEL.get(r) ?? r;

const RESULTADO_COLOR: Record<string, 'warning' | 'success' | 'error' | 'default'> = {
  pendiente: 'warning',
  aceptada: 'success',
  rechazada: 'error',
};

function formatConfianza(c: number): string {
  return `${Math.round(c * 100)}%`;
}

// ── Página ──────────────────────────────────────────────────────────────────

const AgentesPage: React.FC = () => {
  const queryClient = useQueryClient();
  const [filtroAgente, setFiltroAgente] = useState<Agente | ''>('');
  const [filtroResultado, setFiltroResultado] = useState<ResultadoHumano | ''>('');
  const [errorMsg, setErrorMsg] = useState('');

  const { data: predicciones = [], isLoading } = useQuery({
    queryKey: agentesKeys.predicciones(filtroAgente, filtroResultado),
    queryFn: () =>
      prediccionesService.getAll({
        agente: filtroAgente || undefined,
        resultado_humano: filtroResultado || undefined,
      }),
  });

  const invalidarPredicciones = () =>
    queryClient.invalidateQueries({ queryKey: agentesKeys.prediccionesAll() });

  const responder = useMutation({
    mutationFn: ({ id, accion }: { id: string; accion: 'aceptar' | 'rechazar' }) =>
      prediccionesService.responder(id, { accion }),
    onSuccess: invalidarPredicciones,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo responder la sugerencia.')),
  });

  const evaluar = useMutation({
    mutationFn: ({ id, resultado }: { id: string; resultado: 'aceptada' | 'rechazada' }) =>
      prediccionesService.evaluar(id, { resultado_humano: resultado }),
    onSuccess: invalidarPredicciones,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo evaluar la predicción.')),
  });

  const columns: Column<PrediccionAgente>[] = [
    { key: 'agente', header: 'Agente', render: (p) => labelAgente(p.agente) },
    {
      key: 'categoria_predicha',
      header: 'Predicción',
      render: (p) => p.categoria_predicha,
    },
    {
      key: 'confianza',
      header: 'Confianza',
      render: (p) => formatConfianza(p.confianza),
    },
    {
      key: 'resultado_humano',
      header: 'Resultado',
      render: (p) => (
        <StatusChip
          value={p.resultado_humano}
          label={labelResultado(p.resultado_humano)}
          colorMap={RESULTADO_COLOR}
        />
      ),
    },
    {
      key: 'fecha_prediccion',
      header: 'Fecha',
      render: (p) => new Date(p.fecha_prediccion).toLocaleString('es-VE'),
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (p) => {
        const pendiente = p.resultado_humano === 'pendiente';
        const ocupado = responder.isPending || evaluar.isPending;
        if (pendiente) {
          return (
            <Stack direction="row" spacing={1}>
              <Button
                size="small"
                color="success"
                disabled={ocupado}
                onClick={() => responder.mutate({ id: p.id_prediccion, accion: 'aceptar' })}
              >
                Aceptar
              </Button>
              <Button
                size="small"
                color="error"
                disabled={ocupado}
                onClick={() => responder.mutate({ id: p.id_prediccion, accion: 'rechazar' })}
              >
                Rechazar
              </Button>
            </Stack>
          );
        }
        // Ya respondida: permitir re-evaluar (corregir el juicio humano).
        const reEvaluar: 'aceptada' | 'rechazada' =
          p.resultado_humano === 'aceptada' ? 'rechazada' : 'aceptada';
        return (
          <Button
            size="small"
            variant="outlined"
            disabled={ocupado}
            onClick={() => evaluar.mutate({ id: p.id_prediccion, resultado: reEvaluar })}
          >
            Marcar {labelResultado(reEvaluar)}
          </Button>
        );
      },
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Agentes IA"
        subtitle="Predicciones y sugerencias de los agentes inteligentes: revisión, evaluación y análisis."
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      <PanelAnalisis onError={setErrorMsg} onAnalisis={invalidarPredicciones} />

      <MetricasClasificadorSection />

      <Typography variant="h6" sx={{ mt: 1, mb: 1.5 }}>
        Predicciones
      </Typography>

      <Stack direction="row" spacing={2} sx={{ mb: 2 }}>
        <TextField
          select
          label="Agente"
          value={filtroAgente}
          onChange={(e) => setFiltroAgente(e.target.value as Agente | '')}
          size="small"
          sx={{ minWidth: 240 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {AGENTES.map((a) => (
            <MenuItem key={a} value={a}>
              {labelAgente(a)}
            </MenuItem>
          ))}
        </TextField>
        <TextField
          select
          label="Resultado"
          value={filtroResultado}
          onChange={(e) => setFiltroResultado(e.target.value as ResultadoHumano | '')}
          size="small"
          sx={{ minWidth: 200 }}
        >
          <MenuItem value="">Todos</MenuItem>
          {RESULTADOS_HUMANOS.map((r) => (
            <MenuItem key={r} value={r}>
              {labelResultado(r)}
            </MenuItem>
          ))}
        </TextField>
      </Stack>

      <DataTable
        columns={columns}
        rows={predicciones}
        getRowKey={(p) => p.id_prediccion}
        loading={isLoading}
        emptyMessage="Sin predicciones registradas todavía."
      />
    </PageContainer>
  );
};

// ── Panel de análisis (dispara los agentes) ──────────────────────────────────

interface PanelAnalisisProps {
  onError: (msg: string) => void;
  onAnalisis: () => void;
}

const PanelAnalisis: React.FC<PanelAnalisisProps> = ({ onError, onAnalisis }) => {
  const [resultado, setResultado] = useState<string>('');
  const [gastoId, setGastoId] = useState('');
  const [aplicarGasto, setAplicarGasto] = useState(false);

  const mostrar = (titulo: string, data: unknown) => {
    setResultado(`${titulo}\n\n${JSON.stringify(data, null, 2)}`);
  };

  const cobranza = useMutation({
    mutationFn: () => prediccionesService.analizarCobranza(),
    onSuccess: (d) => {
      mostrar('Análisis de cobranza', d);
      onAnalisis();
    },
    onError: (e: unknown) => onError(mensajeDeError(e, 'No se pudo analizar la cobranza.')),
  });

  const reorden = useMutation({
    mutationFn: () => prediccionesService.analizarReorden(),
    onSuccess: (d) => {
      mostrar('Análisis de reorden', d);
      onAnalisis();
    },
    onError: (e: unknown) => onError(mensajeDeError(e, 'No se pudo analizar el reorden.')),
  });

  const personalizacion = useMutation({
    mutationFn: () => prediccionesService.analizarPersonalizacion(),
    onSuccess: (d) => {
      mostrar('Análisis de personalización', d);
      onAnalisis();
    },
    onError: (e: unknown) =>
      onError(mensajeDeError(e, 'No se pudo analizar la personalización.')),
  });

  const clasificar = useMutation({
    mutationFn: () =>
      prediccionesService.clasificarGasto({ gasto_id: gastoId.trim(), aplicar: aplicarGasto }),
    onSuccess: (d) => {
      mostrar('Clasificación de gasto', d);
      onAnalisis();
    },
    onError: (e: unknown) => onError(mensajeDeError(e, 'No se pudo clasificar el gasto.')),
  });

  const ocupado =
    cobranza.isPending || reorden.isPending || personalizacion.isPending || clasificar.isPending;

  const handleClasificar = () => {
    if (!gastoId.trim()) {
      onError('Indique el ID del gasto a clasificar.');
      return;
    }
    clasificar.mutate();
  };

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
          <AutoAwesomeOutlined color="primary" />
          <Typography variant="h6">Disparar análisis</Typography>
        </Stack>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mb: 2 }}>
          <Button
            variant="contained"
            disabled={ocupado}
            onClick={() => cobranza.mutate()}
            startIcon={cobranza.isPending ? <CircularProgress size={16} /> : undefined}
          >
            Analizar cobranza
          </Button>
          <Button
            variant="contained"
            disabled={ocupado}
            onClick={() => reorden.mutate()}
            startIcon={reorden.isPending ? <CircularProgress size={16} /> : undefined}
          >
            Analizar reorden
          </Button>
          <Button
            variant="contained"
            disabled={ocupado}
            onClick={() => personalizacion.mutate()}
            startIcon={personalizacion.isPending ? <CircularProgress size={16} /> : undefined}
          >
            Analizar personalización
          </Button>
        </Stack>

        <Divider sx={{ my: 2 }} />

        <Typography variant="subtitle2" sx={{ mb: 1 }}>
          Clasificar gasto
        </Typography>
        <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap" useFlexGap>
          <TextField
            label="ID del gasto"
            value={gastoId}
            onChange={(e) => setGastoId(e.target.value)}
            size="small"
            sx={{ minWidth: 280 }}
          />
          <TextField
            select
            label="Aplicar"
            value={aplicarGasto ? 'si' : 'no'}
            onChange={(e) => setAplicarGasto(e.target.value === 'si')}
            size="small"
            sx={{ minWidth: 140 }}
          >
            <MenuItem value="no">Solo predecir</MenuItem>
            <MenuItem value="si">Aplicar al gasto</MenuItem>
          </TextField>
          <Button
            variant="outlined"
            disabled={ocupado}
            onClick={handleClasificar}
            startIcon={clasificar.isPending ? <CircularProgress size={16} /> : undefined}
          >
            Clasificar
          </Button>
        </Stack>

        {resultado && (
          <Paper
            variant="outlined"
            sx={{
              mt: 2,
              p: 2,
              maxHeight: 320,
              overflow: 'auto',
              bgcolor: '#1e1e1e',
              color: '#d4d4d4',
              fontFamily: 'monospace',
              fontSize: '0.8rem',
              whiteSpace: 'pre-wrap',
              wordBreak: 'break-word',
            }}
          >
            {resultado}
          </Paper>
        )}
      </CardContent>
    </Card>
  );
};

// ── Métricas del clasificador ─────────────────────────────────────────────────

const MetricasClasificadorSection: React.FC = () => {
  const { data, isLoading, isError } = useQuery({
    queryKey: agentesKeys.metricasClasificador(),
    queryFn: () => prediccionesService.metricasClasificador(),
  });

  return (
    <Card variant="outlined" sx={{ mb: 3 }}>
      <CardContent>
        <Typography variant="h6" sx={{ mb: 1.5 }}>
          Métricas del clasificador de gastos
        </Typography>
        {isLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
            <CircularProgress size={24} />
          </Box>
        ) : isError || !data ? (
          <Typography variant="body2" color="text.secondary">
            No se pudieron cargar las métricas.
          </Typography>
        ) : (
          <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
            <Metrica label="Total" valor={String(data.total)} />
            <Metrica label="Evaluadas" valor={String(data.evaluadas)} />
            <Metrica label="Precisión" valor={`${Math.round(data.precision * 100)}%`} />
            <Metrica
              label="Confianza promedio"
              valor={`${Math.round(data.confianza_promedio * 100)}%`}
            />
            <Metrica label="Latencia promedio" valor={`${data.latencia_promedio_ms} ms`} />
          </Stack>
        )}
      </CardContent>
    </Card>
  );
};

const Metrica: React.FC<{ label: string; valor: string }> = ({ label, valor }) => (
  <Box>
    <Typography variant="caption" color="text.secondary">
      {label}
    </Typography>
    <Typography variant="h6">{valor}</Typography>
  </Box>
);

export default AgentesPage;
