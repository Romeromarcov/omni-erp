import React, { useEffect, useRef, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
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
  type ConsumoLLMResumen,
  type EjecucionAgente,
  type ResultadoHumano,
  type PrediccionAgente,
} from '../../services/agentesService';
import { agentesKeys } from '../../lib/queryKeys';
import { formatoDecimal } from '../../lib/decimal';
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

const ESTADO_EJECUCION_LABEL = new Map<string, string>([
  ['pendiente', 'Pendiente'],
  ['ejecutando', 'Ejecutando'],
  ['completado', 'Completado'],
  ['fallido', 'Fallido'],
]);

const labelAgente = (a: string): string => AGENTE_LABEL.get(a) ?? a;
const labelResultado = (r: string): string => RESULTADO_LABEL.get(r) ?? r;
const labelEstadoEjecucion = (e: string): string => ESTADO_EJECUCION_LABEL.get(e) ?? e;

const USO_LLM_LABEL = new Map<string, string>([
  ['agente', 'Agentes'],
  ['chat', 'Asistente Chat'],
  ['analisis', 'Análisis CxC'],
]);

const labelUsoLlm = (u: string): string => USO_LLM_LABEL.get(u) ?? u;

const RESULTADO_COLOR: Record<string, 'warning' | 'success' | 'error' | 'default'> = {
  pendiente: 'warning',
  aceptada: 'success',
  rechazada: 'error',
};

const ESTADO_EJECUCION_COLOR: Record<string, 'warning' | 'info' | 'success' | 'error' | 'default'> = {
  pendiente: 'warning',
  ejecutando: 'info',
  completado: 'success',
  fallido: 'error',
};

function formatConfianza(c: number): string {
  return `${Math.round(c * 100)}%`;
}

// ── Página ──────────────────────────────────────────────────────────────────

export interface AgentesPageProps {
  pollIntervalMs?: number;
}

const AgentesPage: React.FC<AgentesPageProps> = ({ pollIntervalMs = 1000 }) => {
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

  const invalidarPredicciones = () => {
    void queryClient.invalidateQueries({ queryKey: agentesKeys.prediccionesAll() });
    void queryClient.invalidateQueries({ queryKey: agentesKeys.consumoLlmAll() });
  };

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

      <PanelAnalisis
        pollIntervalMs={pollIntervalMs}
        onError={setErrorMsg}
        onAnalisis={invalidarPredicciones}
      />

      <MetricasClasificadorSection />

      <ConsumoLlmSection />

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

// ── Panel de análisis (encola y realiza polling de ejecuciones) ───────────────

interface PanelAnalisisProps {
  pollIntervalMs: number;
  onError: (msg: string) => void;
  onAnalisis: () => void;
}

const PanelAnalisis: React.FC<PanelAnalisisProps> = ({ pollIntervalMs, onError, onAnalisis }) => {
  const [resultado, setResultado] = useState<string>('');
  const [gastoId, setGastoId] = useState('');
  const [aplicarGasto, setAplicarGasto] = useState(false);
  const [agenteActivo, setAgenteActivo] = useState<Agente | null>(null);
  const [ejecucionActual, setEjecucionActual] = useState<EjecucionAgente<unknown> | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    return () => {
      abortRef.current?.abort();
    };
  }, []);

  const mostrar = (titulo: string, data: unknown) => {
    setResultado(`${titulo}\n\n${JSON.stringify(data, null, 2)}`);
  };

  const ejecutarEnSegundoPlano = async <T,>(
    agente: Agente,
    titulo: string,
    mensajeFalloFallback: string,
    disparar: () => Promise<EjecucionAgente<T>>,
  ) => {
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;

    setAgenteActivo(agente);
    setEjecucionActual(null);
    onError('');

    try {
      const inicial = await disparar();
      if (controller.signal.aborted) return;
      setEjecucionActual(inicial);

      const finalEj = await prediccionesService.esperarEjecucion<T>(inicial, {
        intervalMs: pollIntervalMs,
        signal: controller.signal,
        onEstado: (ej) => {
          if (!controller.signal.aborted) setEjecucionActual(ej);
        },
      });
      if (controller.signal.aborted) return;

      if (finalEj.estado === 'fallido') {
        onError(finalEj.mensaje_error || mensajeFalloFallback);
        return;
      }

      mostrar(titulo, finalEj.resultado);
      onAnalisis();
    } catch (e: unknown) {
      if (controller.signal.aborted || (e instanceof DOMException && e.name === 'AbortError')) {
        return;
      }
      onError(mensajeDeError(e, mensajeFalloFallback));
    } finally {
      if (!controller.signal.aborted) {
        setAgenteActivo(null);
      }
    }
  };

  const ocupado = agenteActivo !== null;

  const handleClasificar = () => {
    if (!gastoId.trim()) {
      onError('Indique el ID del gasto a clasificar.');
      return;
    }
    void ejecutarEnSegundoPlano(
      'clasificador_gastos',
      'Clasificación de gasto',
      'No se pudo clasificar el gasto.',
      () => prediccionesService.clasificarGasto({ gasto_id: gastoId.trim(), aplicar: aplicarGasto }),
    );
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
            onClick={() =>
              void ejecutarEnSegundoPlano(
                'cobranza_estratega',
                'Análisis de cobranza',
                'No se pudo analizar la cobranza.',
                () => prediccionesService.analizarCobranza(),
              )
            }
            startIcon={
              agenteActivo === 'cobranza_estratega' ? <CircularProgress size={16} /> : undefined
            }
          >
            Analizar cobranza
          </Button>
          <Button
            variant="contained"
            disabled={ocupado}
            onClick={() =>
              void ejecutarEnSegundoPlano(
                'reorden_sugeridor',
                'Análisis de reorden',
                'No se pudo analizar el reorden.',
                () => prediccionesService.analizarReorden(),
              )
            }
            startIcon={
              agenteActivo === 'reorden_sugeridor' ? <CircularProgress size={16} /> : undefined
            }
          >
            Analizar reorden
          </Button>
          <Button
            variant="contained"
            disabled={ocupado}
            onClick={() =>
              void ejecutarEnSegundoPlano(
                'personalizacion_capa2',
                'Análisis de personalización',
                'No se pudo analizar la personalización.',
                () => prediccionesService.analizarPersonalizacion(),
              )
            }
            startIcon={
              agenteActivo === 'personalizacion_capa2' ? <CircularProgress size={16} /> : undefined
            }
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
            startIcon={
              agenteActivo === 'clasificador_gastos' ? <CircularProgress size={16} /> : undefined
            }
          >
            Clasificar
          </Button>
        </Stack>

        {ejecucionActual && (
          <Stack
            direction="row"
            spacing={1.5}
            alignItems="center"
            sx={{ mt: 2 }}
            data-testid="estado-ejecucion-agente"
          >
            <Typography variant="body2" color="text.secondary">
              Ejecución {labelAgente(ejecucionActual.agente)}:
            </Typography>
            <StatusChip
              value={ejecucionActual.estado}
              label={labelEstadoEjecucion(ejecucionActual.estado)}
              colorMap={ESTADO_EJECUCION_COLOR}
            />
          </Stack>
        )}

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
            <Metrica label="Evaluadas" valor={String(data.evaluadas ?? 0)} />
            <Metrica
              label="Precisión"
              valor={
                data.precision !== null && data.precision !== undefined
                  ? `${Math.round(data.precision * 100)}%`
                  : '—'
              }
            />
            <Metrica
              label="Confianza promedio"
              valor={
                data.confianza_promedio !== null && data.confianza_promedio !== undefined
                  ? `${Math.round(data.confianza_promedio * 100)}%`
                  : '—'
              }
            />
            <Metrica
              label="Latencia promedio"
              valor={
                data.latencia_promedio_ms !== undefined ? `${data.latencia_promedio_ms} ms` : '—'
              }
            />
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

// ── Consumo LLM (Tokens y Costo USD) ──────────────────────────────────────────

function esResumenConsumoValido(data: unknown): data is ConsumoLLMResumen {
  return (
    Boolean(data) &&
    typeof data === 'object' &&
    !Array.isArray(data) &&
    typeof (data as ConsumoLLMResumen).llamadas === 'number'
  );
}

function formatoUsdPreciso(valor: string | number | null | undefined): string {
  return `$${formatoDecimal(valor ?? '0', 6, 6, 'en-US')} USD`;
}

function formatoTokens(valor: number | null | undefined): string {
  return formatoDecimal(valor ?? 0, 0, 0, 'en-US');
}

const ConsumoLlmSection: React.FC = () => {
  const { data, isLoading, isError } = useQuery({
    queryKey: agentesKeys.consumoLlmResumen(),
    queryFn: () => prediccionesService.obtenerResumenConsumoLLM(),
  });

  const resumen = esResumenConsumoValido(data) ? data : null;
  const porUso = Array.isArray(resumen?.por_uso) ? resumen.por_uso : [];
  const porModelo = Array.isArray(resumen?.por_modelo) ? resumen.por_modelo : [];

  return (
    <Card variant="outlined" sx={{ mb: 3 }} data-testid="consumo-llm-section">
      <CardContent>
        <Typography variant="h6" sx={{ mb: 1.5 }}>
          Consumo LLM (Tokens y Costo USD)
        </Typography>
        {isLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 2 }}>
            <CircularProgress size={24} />
          </Box>
        ) : isError || !resumen ? (
          <Typography variant="body2" color="text.secondary">
            No se pudo cargar el resumen de consumo LLM.
          </Typography>
        ) : resumen.llamadas === 0 ? (
          <Typography variant="body2" color="text.secondary">
            Sin consumo LLM registrado todavía.
          </Typography>
        ) : (
          <Stack spacing={2}>
            <Stack direction="row" spacing={4} flexWrap="wrap" useFlexGap>
              <Metrica label="Llamadas" valor={formatoTokens(resumen.llamadas)} />
              <Metrica label="Tokens entrada" valor={formatoTokens(resumen.tokens_entrada_total)} />
              <Metrica label="Tokens salida" valor={formatoTokens(resumen.tokens_salida_total)} />
              <Metrica label="Costo estimado" valor={formatoUsdPreciso(resumen.costo_total_usd)} />
              <Metrica label="Latencia promedio" valor={`${resumen.latencia_promedio_ms} ms`} />
            </Stack>

            {porUso.length > 0 && (
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.75 }}>
                  Por uso
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {porUso.map((item) => (
                    <Chip
                      key={item.uso}
                      size="small"
                      variant="outlined"
                      label={`${labelUsoLlm(item.uso)}: ${item.llamadas} · ${formatoUsdPreciso(item.costo_total_usd)}`}
                    />
                  ))}
                </Stack>
              </Box>
            )}

            {porModelo.length > 0 && (
              <Box>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.75 }}>
                  Por modelo
                </Typography>
                <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                  {porModelo.map((item) => (
                    <Chip
                      key={item.modelo}
                      size="small"
                      variant="outlined"
                      label={`${item.modelo}: ${item.llamadas} (${formatoTokens(item.tokens_entrada_total)} in / ${formatoTokens(item.tokens_salida_total)} out) · ${formatoUsdPreciso(item.costo_total_usd)}`}
                    />
                  ))}
                </Stack>
              </Box>
            )}
          </Stack>
        )}
      </CardContent>
    </Card>
  );
};

export default AgentesPage;
