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
  DialogContentText,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import { DataTable } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  botUsuariosService,
  CODIGOS_BOT_ESTANDAR,
  type BotUsuario,
  type BotUsuarioPayload,
} from '../../services/botsIngestService';
import { fetchUsuarios } from '../../services/users';
import { botsKeys } from '../../lib/queryKeys';
import { mensajeActivacion } from '../Activaciones/utils';
import { etiquetaBot } from './utils';

const UsuariosBotTab: React.FC = () => {
  const qc = useQueryClient();
  const [errorMsg, setErrorMsg] = useState('');
  const [dialog, setDialog] = useState<BotUsuario | 'nuevo' | null>(null);
  const [borrar, setBorrar] = useState<BotUsuario | null>(null);

  const { data: bots = [], isLoading, isError, error } = useQuery({
    queryKey: botsKeys.usuarios(),
    queryFn: () => botUsuariosService.getAll(),
  });
  const { data: usuarios = [] } = useQuery({
    queryKey: ['core', 'usuarios', 'lista'],
    queryFn: () => fetchUsuarios(),
  });

  const nombreUsuario = (id: string) => {
    const u = usuarios.find((x) => x.id === id);
    return u ? `${`${u.first_name} ${u.last_name}`.trim() || u.username} (${u.username})` : id;
  };

  const eliminar = useMutation({
    mutationFn: (id: string) => botUsuariosService.remove(id),
    onSuccess: () => {
      setBorrar(null);
      void qc.invalidateQueries({ queryKey: botsKeys.usuarios() });
      void qc.invalidateQueries({ queryKey: botsKeys.flota() });
      void qc.invalidateQueries({ queryKey: botsKeys.bitacoraAll() });
    },
    onError: (e: unknown) => {
      setBorrar(null);
      setErrorMsg(mensajeActivacion(e, 'No se pudo quitar al usuario.'));
    },
  });

  const columns: Column<BotUsuario>[] = [
    { key: 'tg', header: 'ID de Telegram', render: (b) => b.telegram_user_id },
    { key: 'nombre', header: 'Nombre', render: (b) => b.nombre || '—' },
    { key: 'usuario', header: 'Vendedor / usuario Omni', render: (b) => nombreUsuario(b.usuario) },
    {
      key: 'bots',
      header: 'Bots permitidos',
      render: (b) =>
        b.bots && b.bots.length > 0 ? (
          <Stack direction="row" spacing={0.5} flexWrap="wrap" useFlexGap>
            {b.bots.map((cod) => (
              <Chip key={cod} size="small" variant="outlined" label={etiquetaBot(cod)} />
            ))}
          </Stack>
        ) : (
          <Chip size="small" color="success" variant="outlined" label="Todos los bots" />
        ),
    },
    {
      key: 'acc',
      header: 'Acciones',
      render: (b) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => setDialog(b)}>
            Editar
          </Button>
          <Button size="small" color="error" onClick={() => setBorrar(b)}>
            Quitar
          </Button>
        </Stack>
      ),
    },
  ];

  return (
    <Box>
      {isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {mensajeActivacion(error, 'No se pudieron cargar los usuarios autorizados.')}
        </Alert>
      )}
      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ sm: 'center' }} sx={{ mb: 2 }}>
        <Alert severity="info" sx={{ flexGrow: 1 }}>
          Solo estos usuarios de Telegram pueden operar los bots de tu empresa. Puedes restringir cada cuenta a bots
          específicos o dejarla habilitada para toda la flota.
        </Alert>
        <Button variant="contained" onClick={() => setDialog('nuevo')}>
          Autorizar usuario
        </Button>
      </Stack>

      <DataTable
        columns={columns}
        rows={bots}
        getRowKey={(b) => b.id_bot_usuario}
        loading={isLoading}
        emptyMessage="Ningún usuario de Telegram autorizado todavía."
      />

      {dialog !== null && (
        <UsuarioBotDialog
          inicial={dialog === 'nuevo' ? null : dialog}
          usuarios={usuarios.map((u) => ({ id: u.id, etiqueta: nombreUsuario(u.id) }))}
          onClose={() => setDialog(null)}
          onSaved={() => {
            setDialog(null);
            void qc.invalidateQueries({ queryKey: botsKeys.usuarios() });
            void qc.invalidateQueries({ queryKey: botsKeys.flota() });
            void qc.invalidateQueries({ queryKey: botsKeys.bitacoraAll() });
          }}
        />
      )}

      <Dialog open={borrar !== null} onClose={() => setBorrar(null)}>
        <DialogTitle>Quitar usuario de Telegram</DialogTitle>
        <DialogContent>
          <DialogContentText>
            ¿Quitar la autorización del ID {borrar?.telegram_user_id}? Dejará de poder enviar datos por los bots.
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setBorrar(null)}>Volver</Button>
          <Button color="error" disabled={eliminar.isPending} onClick={() => borrar && eliminar.mutate(borrar.id_bot_usuario)}>
            Quitar
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
};

const UsuarioBotDialog: React.FC<{
  inicial: BotUsuario | null;
  usuarios: { id: string; etiqueta: string }[];
  onClose: () => void;
  onSaved: () => void;
}> = ({ inicial, usuarios, onClose, onSaved }) => {
  const [tg, setTg] = useState(inicial ? String(inicial.telegram_user_id) : '');
  const [usuario, setUsuario] = useState(inicial?.usuario ?? '');
  const [nombre, setNombre] = useState(inicial?.nombre ?? '');
  const [botsSel, setBotsSel] = useState<string[]>(() => [...(inicial?.bots ?? [])]);
  const [errorMsg, setErrorMsg] = useState('');

  const alternarBot = (codigo: string) => {
    setBotsSel((prev) => (prev.includes(codigo) ? prev.filter((x) => x !== codigo) : [...prev, codigo]));
  };

  const tgLimpio = tg.trim();
  const tgNum = /^\d+$/.test(tgLimpio) ? Number(tgLimpio) : Number.NaN;
  const valido = Number.isSafeInteger(tgNum) && tgNum >= 1 && usuario !== '';

  const guardar = useMutation({
    mutationFn: () => {
      const p: BotUsuarioPayload = {
        telegram_user_id: tgNum,
        usuario,
        nombre: nombre.trim(),
      };
      if (botsSel.length > 0 || (inicial?.bots && inicial.bots.length > 0)) {
        p.bots = botsSel;
      }
      return inicial ? botUsuariosService.update(inicial.id_bot_usuario, p) : botUsuariosService.create(p);
    },
    onSuccess: onSaved,
    onError: (e: unknown) => setErrorMsg(mensajeActivacion(e, 'No se pudo guardar el usuario.')),
  });

  return (
    <Dialog open onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>{inicial ? 'Editar usuario de Telegram' : 'Autorizar usuario de Telegram'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {errorMsg && <Alert severity="error">{errorMsg}</Alert>}
          <TextField
            size="small"
            label="ID numérico de Telegram"
            helperText="Lo obtiene el usuario escribiéndole a @userinfobot."
            value={tg}
            onChange={(e) => setTg(e.target.value)}
            required
          />
          <TextField
            select
            size="small"
            label="Vendedor / usuario Omni"
            value={usuario}
            onChange={(e) => setUsuario(e.target.value)}
            required
          >
            {usuarios.map((u) => (
              <MenuItem key={u.id} value={u.id}>
                {u.etiqueta}
              </MenuItem>
            ))}
          </TextField>
          <TextField size="small" label="Nombre (referencia)" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          <Box>
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.75 }}>
              Bots permitidos (vacío = todos los bots de la empresa)
            </Typography>
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
              {CODIGOS_BOT_ESTANDAR.map((cod) => {
                const activo = botsSel.includes(cod);
                return (
                  <Chip
                    key={cod}
                    size="small"
                    clickable
                    color={activo ? 'primary' : 'default'}
                    variant={activo ? 'filled' : 'outlined'}
                    label={etiquetaBot(cod)}
                    onClick={() => alternarBot(cod)}
                  />
                );
              })}
            </Stack>
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cerrar</Button>
        <Button variant="contained" disabled={!valido || guardar.isPending} onClick={() => guardar.mutate()}>
          Guardar
        </Button>
      </DialogActions>
    </Dialog>
  );
};

export default UsuariosBotTab;
