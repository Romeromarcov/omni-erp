import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { Alert, Box, Button, MenuItem, Stack, TextField, Typography } from '@mui/material';
import { BrandMark, Wordmark } from '../../../components/ui';
import { signup, PLAN_NIVELES, type SignupPayload, type PlanNivel } from '../../../services/saasService';
import { useAuth } from '../../../contexts/AuthContext';

interface FormState {
  empresa_nombre_legal: string;
  empresa_nombre_comercial: string;
  empresa_identificador_fiscal: string;
  empresa_email: string;
  username: string;
  email: string;
  password: string;
  confirm: string;
  first_name: string;
  last_name: string;
  plan_nivel: '' | PlanNivel;
}

const EMPTY: FormState = {
  empresa_nombre_legal: '',
  empresa_nombre_comercial: '',
  empresa_identificador_fiscal: '',
  empresa_email: '',
  username: '',
  email: '',
  password: '',
  confirm: '',
  first_name: '',
  last_name: '',
  plan_nivel: '',
};

/** Extrae un mensaje legible del error JSON del backend (DRF). */
function parseError(err: unknown): string {
  const fallback = 'No se pudo completar el registro. Verifique los datos e intente de nuevo.';
  try {
    const obj = JSON.parse((err as Error).message);
    if (typeof obj?.detail === 'string') return obj.detail;
    // Errores de serializer: { campo: ["msg", ...] }. Object.entries evita el
    // acceso computado obj[firstKey] (CTF-006): clave y valor salen juntos de
    // las propiedades propias del objeto.
    const firstEntry = Object.entries(obj)[0];
    if (firstEntry) {
      const [firstKey, val] = firstEntry;
      const msg = Array.isArray(val) ? val[0] : val;
      return `${firstKey}: ${msg}`;
    }
  } catch {
    /* no era JSON */
  }
  return fallback;
}

const SignupPage: React.FC = () => {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [form, setForm] = useState<FormState>(EMPTY);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const set = <K extends keyof FormState>(key: K, value: FormState[K]) =>
    setForm((f) => ({ ...f, [key]: value }));

  const validate = (): string | null => {
    if (!form.empresa_nombre_legal.trim()) return 'El nombre legal de la empresa es obligatorio.';
    if (!form.username.trim()) return 'El nombre de usuario es obligatorio.';
    if (!form.email.trim()) return 'El email es obligatorio.';
    if (form.password.length < 8) return 'La contraseña debe tener al menos 8 caracteres.';
    if (form.password !== form.confirm) return 'Las contraseñas no coinciden.';
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const err = validate();
    if (err) {
      setError(err);
      return;
    }
    setError('');
    setLoading(true);

    const payload: SignupPayload = {
      empresa_nombre_legal: form.empresa_nombre_legal.trim(),
      empresa_nombre_comercial: form.empresa_nombre_comercial.trim() || undefined,
      empresa_identificador_fiscal: form.empresa_identificador_fiscal.trim() || undefined,
      empresa_email: form.empresa_email.trim() || undefined,
      username: form.username.trim(),
      email: form.email.trim(),
      password: form.password,
      first_name: form.first_name.trim() || undefined,
      last_name: form.last_name.trim() || undefined,
      plan_nivel: form.plan_nivel || undefined,
    };

    try {
      await signup(payload);
      // Cuenta creada en TRIAL. Auto-login reutilizando el flujo seguro de sesión.
      try {
        await login(form.username.trim(), form.password);
        navigate('/dashboard');
      } catch {
        // Si el auto-login no completa (p. ej. paso de dispositivo), enviamos al
        // login normal: la cuenta ya existe y el trial está activo.
        navigate('/login');
      }
    } catch (e2: unknown) {
      setError(parseError(e2));
    } finally {
      setLoading(false);
    }
  };

  const cardStyle: React.CSSProperties = {
    width: '100%',
    maxWidth: 460,
    background: '#fff',
    borderRadius: 20,
    boxShadow: '0 12px 40px rgba(16,42,80,0.12)',
    border: '1px solid rgba(16,42,80,0.06)',
    padding: '32px 28px',
    margin: '16px',
  };

  return (
    <div className="vertical-center">
      <div
        className="centered-container"
        style={{ background: 'linear-gradient(135deg, #e3f0ff 0%, #f6fafd 100%)', overflowY: 'auto' }}
      >
        <div style={cardStyle}>
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1, mb: 2 }}>
            <BrandMark size={48} />
            <Wordmark size={24} />
            <Typography variant="h6" sx={{ textAlign: 'center' }}>
              Crea tu cuenta
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center' }}>
              Prueba gratuita de 30 días · sin tarjeta
            </Typography>
          </Box>

          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          <Box component="form" onSubmit={handleSubmit}>
            <Stack spacing={2}>
              <Typography variant="subtitle2" color="text.secondary">Tu empresa</Typography>
              <TextField
                label="Nombre legal"
                value={form.empresa_nombre_legal}
                onChange={(e) => set('empresa_nombre_legal', e.target.value)}
                required
                fullWidth
                size="small"
              />
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label="Nombre comercial"
                  value={form.empresa_nombre_comercial}
                  onChange={(e) => set('empresa_nombre_comercial', e.target.value)}
                  fullWidth
                  size="small"
                />
                <TextField
                  label="Identificador fiscal (RIF)"
                  value={form.empresa_identificador_fiscal}
                  onChange={(e) => set('empresa_identificador_fiscal', e.target.value)}
                  fullWidth
                  size="small"
                />
              </Stack>
              <TextField
                select
                label="Plan (opcional)"
                value={form.plan_nivel}
                onChange={(e) => set('plan_nivel', e.target.value as FormState['plan_nivel'])}
                fullWidth
                size="small"
                helperText="Si no eliges, se asigna el plan más económico disponible."
              >
                <MenuItem value=""><em>Automático</em></MenuItem>
                {PLAN_NIVELES.map((n) => (
                  <MenuItem key={n} value={n}>{n}</MenuItem>
                ))}
              </TextField>

              <Typography variant="subtitle2" color="text.secondary" sx={{ pt: 1 }}>Tu usuario administrador</Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label="Nombre"
                  value={form.first_name}
                  onChange={(e) => set('first_name', e.target.value)}
                  fullWidth
                  size="small"
                />
                <TextField
                  label="Apellido"
                  value={form.last_name}
                  onChange={(e) => set('last_name', e.target.value)}
                  fullWidth
                  size="small"
                />
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label="Usuario"
                  value={form.username}
                  onChange={(e) => set('username', e.target.value)}
                  required
                  fullWidth
                  size="small"
                  autoComplete="username"
                />
                <TextField
                  label="Email"
                  type="email"
                  value={form.email}
                  onChange={(e) => set('email', e.target.value)}
                  required
                  fullWidth
                  size="small"
                  autoComplete="email"
                />
              </Stack>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <TextField
                  label="Contraseña"
                  type="password"
                  value={form.password}
                  onChange={(e) => set('password', e.target.value)}
                  required
                  fullWidth
                  size="small"
                  autoComplete="new-password"
                />
                <TextField
                  label="Confirmar contraseña"
                  type="password"
                  value={form.confirm}
                  onChange={(e) => set('confirm', e.target.value)}
                  required
                  fullWidth
                  size="small"
                  autoComplete="new-password"
                />
              </Stack>

              <Button type="submit" variant="contained" fullWidth disabled={loading}>
                {loading ? 'Creando cuenta…' : 'Crear cuenta y empezar'}
              </Button>
              <Button variant="text" fullWidth onClick={() => navigate('/login')} disabled={loading}>
                ¿Ya tienes cuenta? Inicia sesión
              </Button>
            </Stack>
          </Box>
        </div>
      </div>
    </div>
  );
};

export default SignupPage;
