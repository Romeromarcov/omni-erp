import React, { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Divider,
  FormControlLabel,
  IconButton,
  InputAdornment,
  List,
  ListItem,
  ListItemText,
  MenuItem,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import type { SelectChangeEvent } from '@mui/material';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import { fetchUsuarios } from '../../../services/users';
import type { Usuario } from '../../../services/users';
import { fetchUsuarioRoles } from '../../../services/usuarioRoles';
import type { UsuarioRol } from '../../../services/usuarioRoles';
import { fetchEmpresas } from '../../../services/empresas';
import { fetchAllSucursales } from '../../../services/sucursales';
import { fetchDepartamentos } from '../../../services/departamentos';
import PageLayout from '../../../components/PageLayout';

const MULTI_HELP = 'Mantén presionada la tecla Ctrl (Windows) o Cmd (Mac) para seleccionar varias opciones.';

const UserDetailPage: React.FC = () => {
  const { id_empresa, id } = useParams<{ id_empresa: string; id: string }>();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<{ first_name: string; last_name: string; email: string; empresas: string[]; sucursales: string[]; departamentos: string[] }>({ first_name: '', last_name: '', email: '', empresas: [], sucursales: [], departamentos: [] });
  const [showChangePassword, setShowChangePassword] = useState(false);
  const [oldPassword, setOldPassword] = useState('');
  const [showOldPassword, setShowOldPassword] = useState(false);
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [showConfirmPassword, setShowConfirmPassword] = useState(false);
  const [passwordMessage, setPasswordMessage] = useState('');
  // Quitar validación de admin, todos pueden editar

  // Multi-select MUI emite string[] (o string en autofill); normalizamos a string[].
  // TextField.SelectProps.onChange está tipado como SelectChangeEvent<unknown>,
  // por eso aceptamos unknown y normalizamos.
  const handleMultiSelect =
    (field: 'empresas' | 'sucursales' | 'departamentos') =>
    (e: SelectChangeEvent<unknown>) => {
      const value = e.target.value;
      const list = Array.isArray(value) ? (value as string[]) : [value as string];
      setForm(f => ({ ...f, [field]: list }));
    };

  const { data: allData, isLoading: loading } = useQuery({
    queryKey: ['/api/core/usuarios-detalle/', id, id_empresa],
    queryFn: async () => {
      const [usuariosRaw, usuarioRolesData, empresasData, sucursalesData, departamentosData] = await Promise.all([
        fetchUsuarios(id_empresa),
        fetchUsuarioRoles(id || ''),
        fetchEmpresas(),
        fetchAllSucursales(),
        fetchDepartamentos(),
      ]);
      let usuarios: Usuario[] = [];
      if (Array.isArray(usuariosRaw)) usuarios = usuariosRaw;
      else if (usuariosRaw && typeof usuariosRaw === 'object' && 'results' in usuariosRaw && Array.isArray((usuariosRaw as { results?: unknown }).results)) {
        usuarios = (usuariosRaw as { results: Usuario[] }).results;
      }
      const user = usuarios.find(u => u.id === id) || null;
      return { usuario: user, usuarioRoles: usuarioRolesData as UsuarioRol[], empresas: empresasData, sucursales: sucursalesData, departamentos: departamentosData };
    },
    enabled: !!id,
  });

  const usuario = allData?.usuario ?? null;
  const usuarioRoles = allData?.usuarioRoles ?? [];
  const empresas = allData?.empresas ?? [];
  const sucursales = allData?.sucursales ?? [];
  const departamentos = allData?.departamentos ?? [];

  // Sync form when usuario loads
  useEffect(() => {
    if (usuario) {
      setForm({
        first_name: usuario.first_name,
        last_name: usuario.last_name,
        email: usuario.email,
        empresas: Array.isArray(usuario.empresas) ? usuario.empresas.map(e => typeof e === 'string' ? e : String(e.id_empresa)) : [],
        sucursales: Array.isArray(usuario.sucursales) ? usuario.sucursales.map(s => typeof s === 'string' ? s : String(s.id_sucursal)) : [],
        departamentos: Array.isArray(usuario.departamentos) ? usuario.departamentos.map(d => typeof d === 'string' ? d : String(d.id_departamento)) : []
      });
    }
  }, [usuario]);

  const updateMutation = useMutation({
    mutationFn: async () => {
      if (!usuario) return;
      const { updateUsuario } = await import('../../../services/users');
      await updateUsuario(usuario.id, { first_name: form.first_name, last_name: form.last_name, email: form.email, empresas: form.empresas, sucursales: form.sucursales, departamentos: form.departamentos });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['/api/core/usuarios-detalle/', id, id_empresa] });
      alert('Usuario actualizado correctamente');
    },
    onError: () => alert('Error al actualizar usuario'),
  });

  if (loading) return (
    <PageLayout maxWidth={540}><Typography>Cargando...</Typography></PageLayout>
  );
  if (!usuario) return (
    <PageLayout maxWidth={540}><Typography>Usuario no encontrado</Typography></PageLayout>
  );

  const empresasAsignadas = empresas.filter(e => form.empresas.includes(String(e.id_empresa))).map(e => e.nombre_comercial || e.nombre_legal).join(', ') || 'Ninguna';
  const sucursalesAsignadas = sucursales.filter(s => form.sucursales.includes(String(s.id_sucursal))).map(s => s.nombre).join(', ') || 'Ninguna';
  const departamentosAsignados = departamentos.filter(d => form.departamentos.includes(String(d.id_departamento))).map(d => d.nombre_departamento).join(', ') || 'Ninguno';

  return (
    <PageLayout maxWidth={540}>
      <Typography variant="h5" mb={3}>Detalle/Edición de Usuario</Typography>
      <Box component="form">
        <Stack spacing={2}>
          <TextField label="Username" value={usuario.username} InputProps={{ readOnly: true }} fullWidth />
          <TextField label="Email" value={form.email} onChange={e => setForm(f => ({ ...f, email: e.target.value }))} fullWidth />
          <TextField label="Nombre" value={form.first_name} onChange={e => setForm(f => ({ ...f, first_name: e.target.value }))} fullWidth />
          <TextField label="Apellido" value={form.last_name} onChange={e => setForm(f => ({ ...f, last_name: e.target.value }))} fullWidth />
          <FormControlLabel control={<Checkbox checked={usuario.is_active} readOnly />} label="Activo" />

          <Box>
            <Typography variant="body2" color="primary"><b>Empresas asignadas:</b> {empresasAsignadas}</Typography>
            <TextField
              select
              label="Empresas"
              value={form.empresas}
              fullWidth
              SelectProps={{ multiple: true, onChange: handleMultiSelect('empresas') }}
              helperText={MULTI_HELP}
              sx={{ mt: 1 }}
            >
              {empresas.map(e => (
                <MenuItem key={e.id_empresa} value={e.id_empresa}>{e.nombre_comercial || e.nombre_legal}</MenuItem>
              ))}
            </TextField>
          </Box>

          <Box>
            <Typography variant="body2" color="primary"><b>Sucursales asignadas:</b> {sucursalesAsignadas}</Typography>
            <TextField
              select
              label="Sucursales"
              value={form.sucursales}
              fullWidth
              SelectProps={{ multiple: true, onChange: handleMultiSelect('sucursales') }}
              helperText={MULTI_HELP}
              sx={{ mt: 1 }}
            >
              {sucursales.map(s => (
                <MenuItem key={s.id_sucursal} value={s.id_sucursal}>{s.nombre}</MenuItem>
              ))}
            </TextField>
          </Box>

          <Box>
            <Typography variant="body2" color="primary"><b>Departamentos asignados:</b> {departamentosAsignados}</Typography>
            <TextField
              select
              label="Departamentos"
              value={form.departamentos}
              fullWidth
              SelectProps={{ multiple: true, onChange: handleMultiSelect('departamentos') }}
              helperText={MULTI_HELP}
              sx={{ mt: 1 }}
            >
              {departamentos.map(d => (
                <MenuItem key={d.id_departamento} value={d.id_departamento}>{d.nombre_departamento}</MenuItem>
              ))}
            </TextField>
          </Box>

          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button
              type="button"
              variant="contained"
              onClick={() => updateMutation.mutate()}
              disabled={updateMutation.isPending}
            >Guardar cambios</Button>
          </Stack>
        </Stack>
      </Box>

      <Divider sx={{ my: 3 }} />
      <Typography variant="h6" mb={1}>Roles asignados</Typography>
      <List dense>
        {usuarioRoles.map(ur => (
          <ListItem key={ur.id_usuario_rol} disableGutters>
            <ListItemText primary={ur.id_rol_nombre} />
          </ListItem>
        ))}
      </List>

      <Button
        variant="outlined"
        sx={{ mb: 2 }}
        onClick={() => setShowChangePassword(s => !s)}
      >
        {showChangePassword ? 'Ocultar cambio de contraseña' : 'Cambiar contraseña'}
      </Button>
      {showChangePassword && (
        <Box
          component="form"
          onSubmit={async e => {
            e.preventDefault();
            setPasswordMessage('');
            if (!oldPassword) {
              setPasswordMessage('Debe ingresar la contraseña actual');
              return;
            }
            if (newPassword !== confirmPassword) {
              setPasswordMessage('Las contraseñas no coinciden');
              return;
            }
            if (!newPassword || newPassword.length < 6) {
              setPasswordMessage('La contraseña debe tener al menos 6 caracteres');
              return;
            }
            try {
              const { changeUserPassword } = await import('../../../services/users');
              await changeUserPassword(oldPassword, newPassword);
              setPasswordMessage('Contraseña actualizada correctamente');
              setOldPassword('');
              setNewPassword('');
              setConfirmPassword('');
            } catch (e) {
              let msg = 'Error al actualizar la contraseña';
              if (e instanceof Error) {
                try {
                  const errObj = JSON.parse(e.message);
                  msg = errObj.error || errObj.message || msg;
                } catch {
                  // No hacer nada, usar mensaje por defecto
                }
              }
              setPasswordMessage(msg);
            }
          }}
        >
          <Stack spacing={2}>
            <TextField
              type={showOldPassword ? 'text' : 'password'}
              label="Contraseña actual"
              value={oldPassword}
              onChange={e => setOldPassword(e.target.value)}
              fullWidth
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={() => setShowOldPassword(v => !v)} edge="end" tabIndex={-1}>
                      {showOldPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
            <TextField
              type={showNewPassword ? 'text' : 'password'}
              label="Nueva contraseña"
              value={newPassword}
              onChange={e => setNewPassword(e.target.value)}
              fullWidth
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={() => setShowNewPassword(v => !v)} edge="end" tabIndex={-1}>
                      {showNewPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
            <TextField
              type={showConfirmPassword ? 'text' : 'password'}
              label="Confirmar contraseña"
              value={confirmPassword}
              onChange={e => setConfirmPassword(e.target.value)}
              fullWidth
              error={!!(confirmPassword && newPassword !== confirmPassword)}
              helperText={confirmPassword && newPassword !== confirmPassword ? 'Las contraseñas no coinciden' : undefined}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <IconButton onClick={() => setShowConfirmPassword(v => !v)} edge="end" tabIndex={-1}>
                      {showConfirmPassword ? <VisibilityOff /> : <Visibility />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
            {passwordMessage && (
              <Alert severity={passwordMessage.includes('correctamente') ? 'success' : 'error'}>{passwordMessage}</Alert>
            )}
            <Stack direction="row" spacing={1} justifyContent="flex-end">
              <Button type="submit" variant="contained">Guardar nueva contraseña</Button>
            </Stack>
          </Stack>
        </Box>
      )}
    </PageLayout>
  );
};

export default UserDetailPage;
