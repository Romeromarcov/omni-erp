import React, { useEffect, useState } from 'react';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Chip,
  Stack,
  TextField,
  Typography,
} from '@mui/material';
import {
  confirmarMfa,
  desactivarMfa,
  getMfaEstado,
  iniciarMfa,
  regenerarCodigosMfa,
  type MfaEstado,
  type MfaIniciarResponse,
} from '../../services/mfa';

function svgToDataUrl(svg: string): string {
  const bytes = new TextEncoder().encode(svg);
  let binary = '';
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return `data:image/svg+xml;base64,${btoa(binary)}`;
}

function parseApiError(err: unknown, fallback: string): string {
  if (err instanceof Error) {
    try {
      const parsed = JSON.parse(err.message) as { error?: string; detail?: string };
      return parsed.error || parsed.detail || fallback;
    } catch {
      return err.message || fallback;
    }
  }
  return fallback;
}

export const MfaConfigSection: React.FC = () => {
  const [estado, setEstado] = useState<MfaEstado | null>(null);
  const [setupData, setSetupData] = useState<MfaIniciarResponse | null>(null);
  const [confirmCode, setConfirmCode] = useState('');
  const [backupCodes, setBackupCodes] = useState<string[] | null>(null);
  const [actionMode, setActionMode] = useState<'none' | 'regenerate' | 'disable'>('none');
  const [actionPassword, setActionPassword] = useState('');
  const [actionCode, setActionCode] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const cargarEstado = async () => {
    try {
      const data = await getMfaEstado();
      setEstado(data);
    } catch {
      setEstado(null);
    }
  };

  useEffect(() => {
    void cargarEstado();
  }, []);

  const handleIniciar = async () => {
    setLoading(true);
    setError('');
    setSuccess('');
    setBackupCodes(null);
    try {
      const data = await iniciarMfa();
      setSetupData(data);
      setConfirmCode('');
    } catch (err) {
      setError(parseApiError(err, 'No se pudo iniciar la configuración 2FA.'));
    } finally {
      setLoading(false);
    }
  };

  const handleConfirmar = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await confirmarMfa(confirmCode.trim());
      setSetupData(null);
      setConfirmCode('');
      setBackupCodes(res.codigos_respaldo);
      setSuccess('Autenticación de dos pasos activada. Guarda tus códigos de respaldo en un lugar seguro.');
      await cargarEstado();
    } catch (err) {
      setError(parseApiError(err, 'Código TOTP inválido.'));
    } finally {
      setLoading(false);
    }
  };

  const handleRegenerar = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await regenerarCodigosMfa(actionCode.trim());
      setBackupCodes(res.codigos_respaldo);
      setActionMode('none');
      setActionCode('');
      setSuccess('Códigos de respaldo regenerados correctamente.');
      await cargarEstado();
    } catch (err) {
      setError(parseApiError(err, 'No se pudieron regenerar los códigos.'));
    } finally {
      setLoading(false);
    }
  };

  const handleDesactivar = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      await desactivarMfa(actionPassword, actionCode.trim());
      setActionMode('none');
      setActionPassword('');
      setActionCode('');
      setBackupCodes(null);
      setSuccess('La autenticación de dos pasos ha sido desactivada.');
      await cargarEstado();
    } catch (err) {
      setError(parseApiError(err, 'No se pudo desactivar el 2FA.'));
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card variant="outlined">
      <CardContent>
        <Stack spacing={2}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 1 }}>
            <Typography variant="h6">Autenticación en dos pasos (2FA / TOTP)</Typography>
            <Chip
              size="small"
              color={estado?.habilitado ? 'success' : 'default'}
              label={estado?.habilitado ? 'Activo' : 'Inactivo'}
            />
          </Box>

          {estado?.requerido_por_politica && !estado.habilitado && (
            <Alert severity="warning">
              Tu empresa recomienda o exige 2FA activo para cuentas administrativas.
            </Alert>
          )}
          {error && <Alert severity="error">{error}</Alert>}
          {success && <Alert severity="success">{success}</Alert>}

          {backupCodes && (
            <Alert severity="info">
              <Typography variant="subtitle2" gutterBottom>
                Códigos de respaldo (se muestran una sola vez):
              </Typography>
              <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1 }}>
                {backupCodes.map((code) => (
                  <Chip key={code} label={code} size="small" variant="outlined" />
                ))}
              </Box>
            </Alert>
          )}

          {!estado?.habilitado && !setupData && (
            <Button variant="contained" onClick={handleIniciar} disabled={loading}>
              Configurar 2FA (TOTP)
            </Button>
          )}

          {setupData && (
            <Box component="form" onSubmit={handleConfirmar} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
              <Typography variant="body2" color="text.secondary">
                Escanea el código QR con tu app autenticadora (Google Authenticator, 1Password, Authy) o ingresa la clave manual:
              </Typography>
              <Box sx={{ display: 'flex', justifyContent: 'center' }}>
                <img
                  src={svgToDataUrl(setupData.qr_svg)}
                  alt="Código QR 2FA"
                  width={180}
                  height={180}
                />
              </Box>
              <TextField
                label="Clave manual"
                value={setupData.secret_manual}
                size="small"
                InputProps={{ readOnly: true }}
                fullWidth
              />
              <TextField
                label="Código de verificación (6 dígitos)"
                value={confirmCode}
                onChange={(e) => setConfirmCode(e.target.value)}
                size="small"
                required
                fullWidth
              />
              <Stack direction="row" spacing={1}>
                <Button type="submit" variant="contained" disabled={loading}>
                  Confirmar y activar 2FA
                </Button>
                <Button variant="text" onClick={() => setSetupData(null)} disabled={loading}>
                  Cancelar
                </Button>
              </Stack>
            </Box>
          )}

          {estado?.habilitado && (
            <>
              <Typography variant="body2" color="text.secondary">
                Códigos de respaldo restantes: {estado.codigos_respaldo_restantes}
              </Typography>
              {actionMode === 'none' && (
                <Stack direction="row" spacing={1} flexWrap="wrap">
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => {
                      setActionMode('regenerate');
                      setActionCode('');
                      setError('');
                    }}
                  >
                    Regenerar códigos
                  </Button>
                  <Button
                    variant="outlined"
                    color="error"
                    size="small"
                    onClick={() => {
                      setActionMode('disable');
                      setActionPassword('');
                      setActionCode('');
                      setError('');
                    }}
                  >
                    Desactivar 2FA
                  </Button>
                </Stack>
              )}

              {actionMode === 'regenerate' && (
                <Box component="form" onSubmit={handleRegenerar} sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                  <TextField
                    label="Código TOTP actual"
                    value={actionCode}
                    onChange={(e) => setActionCode(e.target.value)}
                    size="small"
                    required
                    fullWidth
                  />
                  <Stack direction="row" spacing={1}>
                    <Button type="submit" variant="contained" size="small" disabled={loading}>
                      Generar nuevos códigos
                    </Button>
                    <Button variant="text" size="small" onClick={() => setActionMode('none')}>
                      Cancelar
                    </Button>
                  </Stack>
                </Box>
              )}

              {actionMode === 'disable' && (
                <Box component="form" onSubmit={handleDesactivar} sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                  <TextField
                    type="password"
                    label="Contraseña actual"
                    value={actionPassword}
                    onChange={(e) => setActionPassword(e.target.value)}
                    size="small"
                    required
                    fullWidth
                  />
                  <TextField
                    label="Código TOTP o respaldo"
                    value={actionCode}
                    onChange={(e) => setActionCode(e.target.value)}
                    size="small"
                    required
                    fullWidth
                  />
                  <Stack direction="row" spacing={1}>
                    <Button type="submit" variant="contained" color="error" size="small" disabled={loading}>
                      Confirmar desactivación
                    </Button>
                    <Button variant="text" size="small" onClick={() => setActionMode('none')}>
                      Cancelar
                    </Button>
                  </Stack>
                </Box>
              )}
            </>
          )}
        </Stack>
      </CardContent>
    </Card>
  );
};
