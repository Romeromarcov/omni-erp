import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Switch,
  TextField,
  Typography,
} from '@mui/material';
import { DataTable, KpiCard, SectionTitle } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  botsControlService,
  type BotControlPatchPayload,
  type DetalleBotFlota,
  type EstadoSaludDestino,
  type ResumenBotFlota,
} from '../../services/botsIngestService';
import { botsKeys } from '../../lib/queryKeys';
import { mensajeActivacion } from '../Activaciones/utils';
import { formatearHaceSegundos } from './utils';

const SALUD_LABEL = new Map<EstadoSaludDestino, string>([
  ['ok', 'Operativo'],
  ['error', 'Con fallas'],
  ['desactivado', 'Desactivado'],
  ['sin_clave', 'Sin credencial'],
  ['sin_datos', 'Sin latidos'],
]);

const MODELOS_POR_DEFECTO = ['gemini-2.5-flash', 'gemini-2.5-pro', 'gemini-2.0-flash'] as const;
const MAX_CHAT_ID = 1e15;

const FlotaControlTab: React.FC = () => {
  const qc = useQueryClient();
  const [errorMsg, setErrorMsg] = useState('');
  const [botConfigurando, setBotConfigurando] = useState<string | null>(null);

  const { data: flota = [], isLoading, isError, error } = useQuery({
    queryKey: botsKeys.flota(),
    queryFn: () => botsControlService.listarFlota(),
  });

  const { data: destinos } = useQuery({
    queryKey: botsKeys.destinos(),
    queryFn: () => botsControlService.obtenerDestinos(),
  });

  const alternarEstado = useMutation({
    mutationFn: ({ codigo, habilitado }: { codigo: string; habilitado: boolean }) =>
      botsControlService.actualizarBot(codigo, { habilitado }),
    onSuccess: (_, vars) => {
      void qc.invalidateQueries({ queryKey: botsKeys.flota() });
      void qc.invalidateQueries({ queryKey: botsKeys.botDetalle(vars.codigo) });
      void qc.invalidateQueries({ queryKey: botsKeys.destinos() });
      void qc.invalidateQueries({ queryKey: botsKeys.bitacoraAll() });
    },
    onError: (e: unknown) => setErrorMsg(mensajeActivacion(e, 'No se pudo cambiar el estado del bot.')),
  });

  const columns: Column<ResumenBotFlota>[] = [
    {
      key: 'bot',
      header: 'Bot',
      render: (b) => (
        <Box>
          <Typography variant="body2" fontWeight={600}>
            {b.nombre}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {b.bot}
            {b.version ? ` · v${b.version}` : ''}
          </Typography>
        </Box>
      ),
    },
    {
      key: 'conexion',
      header: 'Conexión',
      render: (b) => (
        <Stack direction="row" spacing={1} alignItems="center">
          <Chip
            size="small"
            color={b.en_linea ? 'success' : b.visto_alguna_vez ? 'warning' : 'default'}
            variant={b.en_linea ? 'filled' : 'outlined'}
            label={b.en_linea ? 'En línea' : b.visto_alguna_vez ? 'Sin latido reciente' : 'Nunca conectado'}
          />
          <Typography variant="caption" color="text.secondary">
            {formatearHaceSegundos(b.hace_segundos)}
          </Typography>
        </Stack>
      ),
    },
    {
      key: 'trafico',
      header: 'Actividad hoy',
      render: (b) => {
        const msg = b.estado.mensajes_hoy ?? 0;
        const err = b.estado.errores_hoy ?? 0;
        return (
          <Stack direction="row" spacing={0.75} alignItems="center">
            <Chip size="small" variant="outlined" label={`${msg} msg`} />
            {err > 0 && <Chip size="small" color="error" variant="outlined" label={`${err} err`} />}
          </Stack>
        );
      },
    },
    {
      key: 'usuarios',
      header: 'Usuarios',
      render: (b) => (b.n_usuarios !== undefined ? String(b.n_usuarios) : '—'),
    },
    {
      key: 'habilitado',
      header: 'Operación',
      render: (b) => (
        <Stack direction="row" spacing={0.75} alignItems="center">
          <Switch
            size="small"
            checked={b.habilitado}
            disabled={alternarEstado.isPending}
            slotProps={{ input: { role: 'switch', 'aria-label': `Habilitar ${b.nombre}` } }}
            onChange={(_, checked) => alternarEstado.mutate({ codigo: b.bot, habilitado: checked })}
          />
          <Typography variant="caption" color={b.habilitado ? 'success.main' : 'warning.main'} fontWeight={600}>
            {b.habilitado ? 'Activo' : 'En pausa'}
          </Typography>
        </Stack>
      ),
    },
    {
      key: 'acc',
      header: 'Acciones',
      render: (b) => (
        <Button size="small" variant="outlined" onClick={() => setBotConfigurando(b.bot)}>
          Configurar
        </Button>
      ),
    },
  ];

  const estadoOmni = destinos?.omni.estado ?? 'sin_datos';
  const estadoGemini = destinos?.gemini.estado ?? 'sin_datos';

  return (
    <Box>
      {isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {mensajeActivacion(error, 'No se pudo cargar la flota de bots.')}
        </Alert>
      )}
      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}

      {destinos && (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', md: 'repeat(4, 1fr)' },
            gap: 2,
            mb: 3,
          }}
        >
          <KpiCard
            label="Flota en línea"
            value={`${destinos.bots_en_linea} / ${destinos.bots_total}`}
            tone={destinos.bots_en_linea > 0 ? 'success' : 'tint'}
            caption="Procesos con latido en los últimos 3 min"
          />
          <KpiCard
            label="Puerta Omni ERP"
            value={SALUD_LABEL.get(estadoOmni) ?? estadoOmni}
            tone={estadoOmni === 'error' ? 'error' : estadoOmni === 'ok' ? 'brand' : 'tint'}
            emphasizeError={estadoOmni === 'error'}
            caption={`Incompletas: ${destinos.ingestas.INCOMPLETO ?? 0} · Sincronizadas: ${destinos.ingestas.SINCRONIZADO ?? 0}`}
          />
          <KpiCard
            label="Extracción IA (Gemini)"
            value={SALUD_LABEL.get(estadoGemini) ?? estadoGemini}
            tone={estadoGemini === 'error' ? 'error' : 'ai'}
            emphasizeError={estadoGemini === 'error'}
            caption="Salud reportada por los bots activos"
          />
          <KpiCard
            label="Cola de reintentos"
            value={destinos.outbox_pendientes}
            tone={destinos.outbox_pendientes > 0 ? 'warning' : 'tint'}
            caption="Borradores pendientes en outbox local"
          />
        </Box>
      )}

      <SectionTitle>Flota de bots de la empresa</SectionTitle>
      <DataTable
        columns={columns}
        rows={flota}
        getRowKey={(b) => b.bot}
        loading={isLoading}
        emptyMessage="No hay bots registrados todavía."
      />

      {botConfigurando && (
        <ConfigurarBotDialog
          codigo={botConfigurando}
          onClose={() => setBotConfigurando(null)}
        />
      )}
    </Box>
  );
};

const ConfigurarBotDialog: React.FC<{ codigo: string; onClose: () => void }> = ({ codigo, onClose }) => {
  const qc = useQueryClient();
  const { data: detalle, isLoading, isError, error } = useQuery({
    queryKey: botsKeys.botDetalle(codigo),
    queryFn: () => botsControlService.obtenerDetalle(codigo),
  });

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="sm">
      {isError ? (
        <>
          <DialogTitle>Error al cargar configuración</DialogTitle>
          <DialogContent>
            <Alert severity="error">
              {mensajeActivacion(error, 'No se pudo cargar la configuración del bot.')}
            </Alert>
          </DialogContent>
          <DialogActions>
            <Button onClick={onClose}>Cerrar</Button>
          </DialogActions>
        </>
      ) : isLoading || !detalle ? (
        <>
          <DialogTitle>Cargando configuración…</DialogTitle>
          <DialogActions>
            <Button onClick={onClose}>Cerrar</Button>
          </DialogActions>
        </>
      ) : (
        <FormularioBotContenido
          key={`${detalle.bot}:${detalle.actualizado_en ?? ''}`}
          detalle={detalle}
          onClose={onClose}
          onSaved={() => {
            void qc.invalidateQueries({ queryKey: botsKeys.flota() });
            void qc.invalidateQueries({ queryKey: botsKeys.botDetalle(codigo) });
            void qc.invalidateQueries({ queryKey: botsKeys.destinos() });
            void qc.invalidateQueries({ queryKey: botsKeys.bitacoraAll() });
            onClose();
          }}
        />
      )}
    </Dialog>
  );
};

const FormularioBotContenido: React.FC<{
  detalle: DetalleBotFlota;
  onClose: () => void;
  onSaved: () => void;
}> = ({ detalle, onClose, onSaved }) => {
  const [nombre, setNombre] = useState(detalle.nombre);
  const [habilitado, setHabilitado] = useState(detalle.habilitado);
  const [mensaje, setMensaje] = useState(detalle.mensaje ?? '');
  const [autoMin, setAutoMin] = useState(String(detalle.parametros.auto_envio_min ?? 10));
  const [modelo, setModelo] = useState(String(detalle.parametros.gemini_model ?? 'gemini-2.5-flash'));
  const [chatGrupo, setChatGrupo] = useState(
    detalle.chats.grupo !== null && detalle.chats.grupo !== undefined ? String(detalle.chats.grupo) : '',
  );
  const [chatRespaldo, setChatRespaldo] = useState(
    detalle.chats.respaldo !== null && detalle.chats.respaldo !== undefined ? String(detalle.chats.respaldo) : '',
  );
  const [urlPanel, setUrlPanel] = useState(detalle.url_panel ?? '');
  const [errorMsg, setErrorMsg] = useState('');

  const modelosOpciones = Array.from(
    new Set([...(detalle.modelos_sugeridos.length ? detalle.modelos_sugeridos : MODELOS_POR_DEFECTO), modelo]),
  );

  const parsearChat = (raw: string): number | null => {
    const limpio = raw.trim();
    if (!limpio) return null;
    if (!/^-?\d+$/.test(limpio)) return Number.NaN;
    const num = Number(limpio);
    if (!Number.isSafeInteger(num) || num === 0 || Math.abs(num) > MAX_CHAT_ID) {
      return Number.NaN;
    }
    return num;
  };

  const minLimpio = autoMin.trim();
  const minNum = /^\d+$/.test(minLimpio) ? Number(minLimpio) : Number.NaN;
  const grupoParsed = parsearChat(chatGrupo);
  const respaldoParsed = parsearChat(chatRespaldo);
  const formularioValido =
    nombre.trim().length > 0 &&
    Number.isSafeInteger(minNum) &&
    minNum >= 1 &&
    minNum <= 120 &&
    !Number.isNaN(grupoParsed) &&
    !Number.isNaN(respaldoParsed);

  const guardar = useMutation({
    mutationFn: () => {
      const payload: BotControlPatchPayload = {
        nombre: nombre.trim(),
        habilitado,
        mensaje: mensaje.trim(),
        url_panel: urlPanel.trim(),
        parametros: {
          auto_envio_min: minNum,
          gemini_model: modelo,
        },
        chats: {
          grupo: grupoParsed,
          respaldo: respaldoParsed,
        },
      };
      return botsControlService.actualizarBot(detalle.bot, payload);
    },
    onSuccess: onSaved,
    onError: (e: unknown) => setErrorMsg(mensajeActivacion(e, 'No se pudo actualizar la configuración del bot.')),
  });

  return (
    <>
      <DialogTitle>
        Configurar {detalle.nombre} ({detalle.bot})
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {errorMsg && <Alert severity="error">{errorMsg}</Alert>}
          {detalle.estado.ultimo_error && (
            <Alert severity="warning">
              Último error reportado: {detalle.estado.ultimo_error}
            </Alert>
          )}
          <FormControlLabel
            control={<Switch checked={habilitado} onChange={(_, v) => setHabilitado(v)} />}
            label={habilitado ? 'Bot habilitado para procesar mensajes' : 'Bot en pausa'}
          />
          <TextField
            size="small"
            label="Nombre visible"
            value={nombre}
            onChange={(e) => setNombre(e.target.value)}
            required
          />
          <TextField
            size="small"
            label="Mensaje de pausa (opcional)"
            helperText="Se envía a usuarios autorizados si el bot está en pausa."
            value={mensaje}
            onChange={(e) => setMensaje(e.target.value)}
          />
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              size="small"
              label="Auto-envío (minutos, 1–120)"
              value={autoMin}
              onChange={(e) => setAutoMin(e.target.value)}
              fullWidth
            />
            <TextField
              select
              size="small"
              label="Modelo Gemini"
              value={modelo}
              onChange={(e) => setModelo(e.target.value)}
              fullWidth
            >
              {modelosOpciones.map((m) => (
                <MenuItem key={m} value={m}>
                  {m}
                </MenuItem>
              ))}
            </TextField>
          </Stack>
          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
            <TextField
              size="small"
              label="ID chat de grupo (ej. -100123456)"
              value={chatGrupo}
              onChange={(e) => setChatGrupo(e.target.value)}
              fullWidth
            />
            <TextField
              size="small"
              label="ID chat de respaldo"
              value={chatRespaldo}
              onChange={(e) => setChatRespaldo(e.target.value)}
              fullWidth
            />
          </Stack>
          <TextField
            size="small"
            label="URL externa de referencia (https://…)"
            value={urlPanel}
            onChange={(e) => setUrlPanel(e.target.value)}
          />

          {detalle.historial.length > 0 && (
            <Box>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Últimos 7 días
              </Typography>
              <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                {detalle.historial.map((h) => (
                  <Chip
                    key={h.dia}
                    size="small"
                    variant="outlined"
                    label={`${h.dia}: ${h.mensajes} msg · ${h.errores} err`}
                  />
                ))}
              </Stack>
            </Box>
          )}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cerrar</Button>
        <Button
          variant="contained"
          disabled={!formularioValido || guardar.isPending}
          onClick={() => guardar.mutate()}
        >
          Guardar configuración
        </Button>
      </DialogActions>
    </>
  );
};

export default FlotaControlTab;
