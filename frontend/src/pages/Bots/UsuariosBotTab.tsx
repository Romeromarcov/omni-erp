import React, { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import { DataTable } from '../../components/ui';
import type { Column } from '../../components/ui';
import { botUsuariosService, type BotUsuario } from '../../services/botsIngestService';
import { fetchUsuarios } from '../../services/users';
import { botsKeys } from '../../lib/queryKeys';
import { mensajeActivacion } from '../Activaciones/utils';

const UsuariosBotTab: React.FC = () => {
  const qc = useQueryClient();
  const [errorMsg, setErrorMsg] = useState('');
  const [dialog, setDialog] = useState<BotUsuario | 'nuevo' | null>(null);
  const [borrar, setBorrar] = useState<BotUsuario | null>(null);

  const { data: bots = [], isLoading } = useQuery({
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
      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}
      <Stack direction="row" sx={{ mb: 2 }}>
        <Alert severity="info" sx={{ flexGrow: 1, mr: 2 }}>
          Solo estos usuarios de Telegram pueden enviar pedidos, pagos y eventos a Omni. El vendedor asociado recibe las
          comisiones de sus pedidos.
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
  const [errorMsg, setErrorMsg] = useState('');

  const guardar = useMutation({
    mutationFn: () => {
      const p = { telegram_user_id: Number(tg), usuario, nombre: nombre.trim() };
      return inicial ? botUsuariosService.update(inicial.id_bot_usuario, p) : botUsuariosService.create(p);
    },
    onSuccess: onSaved,
    onError: (e: unknown) => setErrorMsg(mensajeActivacion(e, 'No se pudo guardar el usuario.')),
  });

  const valido = /^\d+$/.test(tg.trim()) && Number(tg) > 0 && usuario !== '';

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
