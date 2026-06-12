/**
 * Apertura de sesión de caja desde el POS: si no hay sesión ABIERTA, se
 * ofrece elegir una caja física activa y abrir sesión sobre ella
 * (`/finanzas/cajas-fisicas/{id}/abrir-sesion/`).
 */
import { useState } from 'react';
import {
  Alert, Button, CircularProgress, Dialog, DialogActions, DialogContent,
  DialogContentText, DialogTitle, List, ListItemButton, ListItemText,
} from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { cajasFisicasService } from '../../../services/cajasFisicasService';

interface Props {
  open: boolean;
  empresaId: string;
  onAbierta: () => void;
  onClose: () => void;
}

export default function PosSesionDialog({ open, empresaId, onAbierta, onClose }: Props) {
  const [abriendo, setAbriendo] = useState(false);
  const [error, setError] = useState('');

  const { data, isLoading } = useQuery({
    queryKey: ['pos', 'cajas-fisicas', empresaId],
    queryFn: () => cajasFisicasService.getCajasFisicas({ empresa: empresaId, activa: true }),
    enabled: open && !!empresaId,
  });
  const cajas = data?.results ?? [];

  const abrir = async (idCaja: string) => {
    setAbriendo(true);
    setError('');
    try {
      await cajasFisicasService.abrirSesion(idCaja);
      onAbierta();
    } catch {
      setError('No se pudo abrir la sesión de caja. Intenta de nuevo.');
    } finally {
      setAbriendo(false);
    }
  };

  return (
    <Dialog open={open} onClose={abriendo ? undefined : onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Abrir sesión de caja</DialogTitle>
      <DialogContent>
        <DialogContentText sx={{ mb: 1 }}>
          No hay una sesión de caja abierta. Selecciona la caja para empezar a vender.
        </DialogContentText>
        {error && <Alert severity="error" sx={{ mb: 1 }}>{error}</Alert>}
        {isLoading || abriendo ? (
          <CircularProgress size={28} />
        ) : cajas.length === 0 ? (
          <Alert severity="warning">No hay cajas físicas activas configuradas para esta empresa.</Alert>
        ) : (
          <List data-testid="pos-cajas-lista">
            {cajas.map((c) => (
              <ListItemButton key={c.id_caja_fisica} onClick={() => void abrir(c.id_caja_fisica)}>
                <ListItemText primary={c.nombre} secondary={c.sucursal_nombre} />
              </ListItemButton>
            ))}
          </List>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={abriendo}>Cancelar</Button>
      </DialogActions>
    </Dialog>
  );
}
