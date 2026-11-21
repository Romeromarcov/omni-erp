import { useEffect, useState, type FormEvent } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import Alert from '@mui/material/Alert';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import CircularProgress from '@mui/material/CircularProgress';
import Grid from '@mui/material/Grid';
import IconButton from '@mui/material/IconButton';
import MenuItem from '@mui/material/MenuItem';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import AddOutlined from '@mui/icons-material/AddOutlined';
import ContentCopyOutlined from '@mui/icons-material/ContentCopyOutlined';
import DeleteOutlineOutlined from '@mui/icons-material/DeleteOutlineOutlined';
import OpenInNewOutlined from '@mui/icons-material/OpenInNewOutlined';
import SaveOutlined from '@mui/icons-material/SaveOutlined';
import { PageContainer, PageHeader } from '../../components/ui';
import { connectKeys } from '../../lib/queryKeys';
import {
  getMiPerfil,
  updateMiPerfil,
  type ConnectBoton,
  type ConnectPerfil,
} from '../../services/connectService';
import { mensajeDeError, statusDeError } from '../../utils/api';
import { getEmpresaId } from '../../utils/empresa';

const TEMA_OPCIONES = [
  { value: 'CLASICO', label: 'Clásico' },
  { value: 'MODERNO', label: 'Moderno' },
  { value: 'CORPORATIVO', label: 'Corporativo' },
  { value: 'OSCURO', label: 'Oscuro' },
];

const BOTON_TIPO_OPCIONES = [
  { value: 'web', label: 'Sitio web' },
  { value: 'whatsapp', label: 'WhatsApp' },
  { value: 'instagram', label: 'Instagram' },
  { value: 'catalogo', label: 'Catálogo' },
  { value: 'pago', label: 'Enlace de pago' },
  { value: 'ubicacion', label: 'Ubicación' },
  { value: 'telefono', label: 'Teléfono' },
  { value: 'correo', label: 'Correo electrónico' },
];

export default function ConnectPerfilPage() {
  const empresaId = getEmpresaId();
  const queryClient = useQueryClient();

  const [slug, setSlug] = useState('');
  const [nombrePublico, setNombrePublico] = useState('');
  const [cargo, setCargo] = useState('');
  const [bio, setBio] = useState('');
  const [telefonoPublico, setTelefonoPublico] = useState('');
  const [emailPublico, setEmailPublico] = useState('');
  const [tema, setTema] = useState('CLASICO');
  const [botones, setBotones] = useState<ConnectBoton[]>([]);
  const [copiado, setCopiado] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  const perfilQuery = useQuery<ConnectPerfil | null>({
    queryKey: connectKeys.miPerfil(empresaId),
    queryFn: async () => {
      try {
        return await getMiPerfil(empresaId);
      } catch (err) {
        if (statusDeError(err) === 404) {
          return null;
        }
        throw err;
      }
    },
  });

  useEffect(() => {
    const perfil = perfilQuery.data;
    if (!perfil) return;
    setSlug(perfil.slug || '');
    setNombrePublico(perfil.nombre_publico || '');
    setCargo(perfil.cargo || '');
    setBio(perfil.bio || '');
    setTelefonoPublico(perfil.telefono_publico || '');
    setEmailPublico(perfil.email_publico || '');
    setTema(perfil.tema || 'CLASICO');
    setBotones(Array.isArray(perfil.botones) ? perfil.botones : []);
  }, [perfilQuery.data]);

  const saveMutation = useMutation({
    mutationFn: () =>
      updateMiPerfil(
        {
          slug: slug.trim().toLowerCase(),
          nombre_publico: nombrePublico.trim(),
          cargo: cargo.trim(),
          bio: bio.trim(),
          telefono_publico: telefonoPublico.trim(),
          email_publico: emailPublico.trim(),
          tema,
          botones: botones.map((b) => ({
            tipo: b.tipo,
            etiqueta: b.etiqueta.trim(),
            valor: b.valor.trim(),
          })),
        },
        empresaId,
      ),
    onSuccess: (updated) => {
      queryClient.setQueryData(connectKeys.miPerfil(empresaId), updated);
      setSaveError(null);
      setSaveSuccess('Perfil guardado correctamente.');
    },
    onError: (err) => {
      setSaveSuccess(null);
      setSaveError(mensajeDeError(err, 'No se pudo guardar el perfil Connect.'));
    },
  });

  const plantillaBloqueada = Boolean(perfilQuery.data?.plantilla_bloqueada);
  const slugLimpio = slug.trim().toLowerCase();
  const publicPath = slugLimpio ? `/c/${slugLimpio}` : '';
  const publicUrl =
    publicPath && typeof window !== 'undefined' ? `${window.location.origin}${publicPath}` : publicPath;

  function handleAddBoton() {
    if (botones.length >= 30) return;
    setBotones((prev) => [...prev, { tipo: 'web', etiqueta: '', valor: '' }]);
  }

  function handleUpdateBoton(index: number, patch: Partial<ConnectBoton>) {
    setBotones((prev) =>
      prev.map((item, idx) => (idx === index ? { ...item, ...patch } : item)),
    );
  }

  function handleRemoveBoton(index: number) {
    setBotones((prev) => prev.filter((_, idx) => idx !== index));
  }

  async function handleCopyUrl() {
    if (!publicUrl || !navigator.clipboard?.writeText) return;
    await navigator.clipboard.writeText(publicUrl);
    setCopiado(true);
    window.setTimeout(() => setCopiado(false), 2000);
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setSaveSuccess(null);
    setSaveError(null);
    if (!slugLimpio || !nombrePublico.trim()) {
      setSaveError('El slug público y el nombre público son obligatorios.');
      return;
    }
    saveMutation.mutate();
  }

  if (perfilQuery.isLoading) {
    return (
      <PageContainer>
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      </PageContainer>
    );
  }

  if (perfilQuery.isError) {
    return (
      <PageContainer>
        <PageHeader title="Mi perfil digital" subtitle="Tarjeta pública Omni Connect" />
        <Alert severity="error">
          {mensajeDeError(perfilQuery.error, 'No se pudo cargar tu perfil Connect.')}
        </Alert>
      </PageContainer>
    );
  }

  return (
    <PageContainer>
      <PageHeader
        title="Mi perfil digital"
        subtitle="Personaliza tu tarjeta NFC/QR de Omni Connect y comparte tu enlace público."
      />

      <Grid container spacing={3}>
        <Grid size={{ xs: 12, md: 8 }}>
          <Card>
            <CardContent>
              {perfilQuery.data === null && (
                <Alert severity="info" sx={{ mb: 2 }}>
                  Aún no has creado tu tarjeta digital en esta empresa. Completa los campos y guarda para activarla.
                </Alert>
              )}

              {plantillaBloqueada && (
                <Alert severity="warning" sx={{ mb: 2 }}>
                  La plantilla visual está bloqueada por el administrador de tu empresa.
                </Alert>
              )}

              {saveSuccess && (
                <Alert severity="success" sx={{ mb: 2 }}>
                  {saveSuccess}
                </Alert>
              )}

              {saveError && (
                <Alert severity="error" sx={{ mb: 2 }}>
                  {saveError}
                </Alert>
              )}

              <Box component="form" onSubmit={handleSubmit} noValidate>
                <Stack spacing={2.25}>
                  <Grid container spacing={2}>
                    <Grid size={{ xs: 12, sm: 6 }}>
                      <TextField
                        label="Slug público"
                        required
                        fullWidth
                        value={slug}
                        onChange={(e) => setSlug(e.target.value)}
                        helperText={publicPath ? `URL pública: ${publicPath}` : 'Ej. juan-perez'}
                      />
                    </Grid>
                    <Grid size={{ xs: 12, sm: 6 }}>
                      <TextField
                        label="Nombre público"
                        required
                        fullWidth
                        value={nombrePublico}
                        onChange={(e) => setNombrePublico(e.target.value)}
                      />
                    </Grid>
                    <Grid size={{ xs: 12, sm: 6 }}>
                      <TextField
                        label="Cargo"
                        fullWidth
                        value={cargo}
                        onChange={(e) => setCargo(e.target.value)}
                      />
                    </Grid>
                    <Grid size={{ xs: 12, sm: 6 }}>
                      <TextField
                        select
                        label="Tema visual"
                        fullWidth
                        value={tema}
                        disabled={plantillaBloqueada}
                        onChange={(e) => setTema(e.target.value)}
                      >
                        {TEMA_OPCIONES.map((opt) => (
                          <MenuItem key={opt.value} value={opt.value}>
                            {opt.label}
                          </MenuItem>
                        ))}
                      </TextField>
                    </Grid>
                    <Grid size={{ xs: 12, sm: 6 }}>
                      <TextField
                        label="Teléfono público"
                        fullWidth
                        value={telefonoPublico}
                        onChange={(e) => setTelefonoPublico(e.target.value)}
                      />
                    </Grid>
                    <Grid size={{ xs: 12, sm: 6 }}>
                      <TextField
                        label="Correo público"
                        type="email"
                        fullWidth
                        value={emailPublico}
                        onChange={(e) => setEmailPublico(e.target.value)}
                      />
                    </Grid>
                  </Grid>

                  <TextField
                    label="Biografía"
                    multiline
                    minRows={3}
                    fullWidth
                    value={bio}
                    onChange={(e) => setBio(e.target.value)}
                  />

                  <Stack direction="row" justifyContent="space-between" alignItems="center">
                    <Typography variant="subtitle1" fontWeight={600}>
                      Botones y enlaces ({botones.length}/30)
                    </Typography>
                    <Button
                      type="button"
                      variant="outlined"
                      size="small"
                      startIcon={<AddOutlined />}
                      onClick={handleAddBoton}
                      disabled={botones.length >= 30}
                    >
                      Agregar botón
                    </Button>
                  </Stack>

                  {botones.map((boton, idx) => (
                    <Grid container spacing={1.5} key={`boton-${idx}`} alignItems="center">
                      <Grid size={{ xs: 12, sm: 3 }}>
                        <TextField
                          select
                          label="Tipo"
                          size="small"
                          fullWidth
                          value={boton.tipo}
                          onChange={(e) => handleUpdateBoton(idx, { tipo: e.target.value })}
                        >
                          {BOTON_TIPO_OPCIONES.map((opt) => (
                            <MenuItem key={opt.value} value={opt.value}>
                              {opt.label}
                            </MenuItem>
                          ))}
                        </TextField>
                      </Grid>
                      <Grid size={{ xs: 12, sm: 4 }}>
                        <TextField
                          label="Etiqueta"
                          size="small"
                          fullWidth
                          value={boton.etiqueta}
                          onChange={(e) => handleUpdateBoton(idx, { etiqueta: e.target.value })}
                        />
                      </Grid>
                      <Grid size={{ xs: 10, sm: 4 }}>
                        <TextField
                          label="Valor / URL"
                          size="small"
                          fullWidth
                          value={boton.valor}
                          onChange={(e) => handleUpdateBoton(idx, { valor: e.target.value })}
                        />
                      </Grid>
                      <Grid size={{ xs: 2, sm: 1 }}>
                        <IconButton
                          aria-label={`Eliminar botón ${idx + 1}`}
                          color="error"
                          onClick={() => handleRemoveBoton(idx)}
                        >
                          <DeleteOutlineOutlined />
                        </IconButton>
                      </Grid>
                    </Grid>
                  ))}

                  <Box sx={{ display: 'flex', justifyContent: 'flex-end' }}>
                    <Button
                      type="submit"
                      variant="contained"
                      startIcon={<SaveOutlined />}
                      disabled={saveMutation.isPending}
                    >
                      {saveMutation.isPending ? 'Guardando…' : 'Guardar perfil'}
                    </Button>
                  </Box>
                </Stack>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        <Grid size={{ xs: 12, md: 4 }}>
          <Card>
            <CardContent>
              <Typography variant="subtitle1" fontWeight={700} gutterBottom>
                Vista previa de enlace público
              </Typography>
              <Typography variant="body2" color="text.secondary" mb={2}>
                Comparte esta URL o grábala en tu chip NFC / código QR:
              </Typography>
              <Box
                sx={{
                  p: 1.5,
                  borderRadius: 1.5,
                  bgcolor: 'action.hover',
                  wordBreak: 'break-all',
                  mb: 2,
                }}
              >
                <Typography variant="body2" fontFamily="monospace">
                  {publicUrl || '/c/tu-slug'}
                </Typography>
              </Box>
              <Stack spacing={1.25}>
                <Button
                  type="button"
                  variant="outlined"
                  startIcon={<ContentCopyOutlined />}
                  onClick={handleCopyUrl}
                  disabled={!publicUrl}
                  fullWidth
                >
                  {copiado ? 'Enlace copiado' : 'Copiar enlace'}
                </Button>
                <Button
                  component="a"
                  href={publicPath || undefined}
                  target="_blank"
                  rel="noopener noreferrer"
                  variant="contained"
                  endIcon={<OpenInNewOutlined />}
                  disabled={!publicPath}
                  fullWidth
                >
                  Abrir tarjeta pública
                </Button>
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </PageContainer>
  );
}
