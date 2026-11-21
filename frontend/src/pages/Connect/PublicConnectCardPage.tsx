import { useEffect, useMemo, useState, type FormEvent } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';
import Alert from '@mui/material/Alert';
import Avatar from '@mui/material/Avatar';
import Box from '@mui/material/Box';
import Button from '@mui/material/Button';
import Card from '@mui/material/Card';
import CardContent from '@mui/material/CardContent';
import Checkbox from '@mui/material/Checkbox';
import Chip from '@mui/material/Chip';
import CircularProgress from '@mui/material/CircularProgress';
import Container from '@mui/material/Container';
import Divider from '@mui/material/Divider';
import FormControlLabel from '@mui/material/FormControlLabel';
import Stack from '@mui/material/Stack';
import TextField from '@mui/material/TextField';
import Typography from '@mui/material/Typography';
import BusinessOutlined from '@mui/icons-material/BusinessOutlined';
import ContactMailOutlined from '@mui/icons-material/ContactMailOutlined';
import DownloadOutlined from '@mui/icons-material/DownloadOutlined';
import EmailOutlined from '@mui/icons-material/EmailOutlined';
import OpenInNewOutlined from '@mui/icons-material/OpenInNewOutlined';
import PhoneOutlined from '@mui/icons-material/PhoneOutlined';
import SendOutlined from '@mui/icons-material/SendOutlined';
import {
  buildHrefSeguro,
  getPublicProfile,
  getPublicVCardUrl,
  submitPublicLead,
  type PublicConnectProfile,
} from '../../services/connectService';
import { mensajeDeError, statusDeError } from '../../utils/api';

const FALLBACK_CONSENT_TEXT =
  'Autorizo a usar mis datos únicamente para contactarme en relación con esta solicitud.';

interface TemaPalette {
  headerBg: string;
  headerText: string;
  chipBg: string;
  pageBg: string;
}

function getTemaPalette(tema: string): TemaPalette {
  switch (tema.toUpperCase()) {
    case 'OSCURO':
      return {
        headerBg: 'linear-gradient(135deg, #0f172a 0%, #1e293b 100%)',
        headerText: '#f8fafc',
        chipBg: 'rgba(248, 250, 252, 0.14)',
        pageBg: '#0b1120',
      };
    case 'MODERNO':
      return {
        headerBg: 'linear-gradient(135deg, #0f766e 0%, #14b8a6 100%)',
        headerText: '#ffffff',
        chipBg: 'rgba(255, 255, 255, 0.18)',
        pageBg: '#f0fdfa',
      };
    case 'CORPORATIVO':
      return {
        headerBg: 'linear-gradient(135deg, #1d4ed8 0%, #1e40af 100%)',
        headerText: '#ffffff',
        chipBg: 'rgba(255, 255, 255, 0.16)',
        pageBg: '#eff6ff',
      };
    default:
      return {
        headerBg: 'linear-gradient(135deg, #1e293b 0%, #334155 100%)',
        headerText: '#ffffff',
        chipBg: 'rgba(255, 255, 255, 0.16)',
        pageBg: '#f8fafc',
      };
  }
}

function getIniciales(nombre: string): string {
  const parts = nombre
    .trim()
    .split(/\s+/)
    .filter((p) => p.length > 0);
  if (parts.length === 0) return 'OC';
  if (parts.length === 1) return parts.at(0)?.slice(0, 2).toUpperCase() ?? 'OC';
  const first = parts.at(0)?.slice(0, 1) ?? '';
  const last = parts.at(-1)?.slice(0, 1) ?? '';
  return `${first}${last}`.toUpperCase();
}

export default function PublicConnectCardPage() {
  const { slug = '' } = useParams<{ slug: string }>();
  const [searchParams] = useSearchParams();
  const uid = searchParams.get('uid') ?? undefined;
  const origenParam = (searchParams.get('origen') ?? searchParams.get('src') ?? '').trim().toUpperCase();

  const [profile, setProfile] = useState<PublicConnectProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [notFound, setNotFound] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [nombre, setNombre] = useState('');
  const [apellido, setApellido] = useState('');
  const [empresaNombre, setEmpresaNombre] = useState('');
  const [email, setEmail] = useState('');
  const [telefono, setTelefono] = useState('');
  const [mensaje, setMensaje] = useState('');
  const [website, setWebsite] = useState('');
  const [consentimientoAceptado, setConsentimientoAceptado] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      if (!slug.trim()) {
        setNotFound(true);
        setLoading(false);
        return;
      }
      setLoading(true);
      setNotFound(false);
      setLoadError(null);
      try {
        const data = await getPublicProfile(slug, uid, origenParam || undefined);
        if (!cancelled) {
          setProfile(data);
        }
      } catch (err) {
        if (cancelled) return;
        if (statusDeError(err) === 404) {
          setNotFound(true);
        } else {
          setLoadError(mensajeDeError(err, 'No se pudo cargar el perfil público.'));
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }
    void load();
    return () => {
      cancelled = true;
    };
  }, [slug, uid, origenParam]);

  const safeButtons = useMemo(() => {
    if (!profile) return [];
    return (profile.botones || [])
      .map((boton, index) => {
        const href = buildHrefSeguro(boton);
        if (!href) return null;
        return {
          key: `${boton.tipo}-${index}-${boton.etiqueta}`,
          etiqueta: boton.etiqueta,
          href,
          isExternalHttp: href.startsWith('http://') || href.startsWith('https://'),
        };
      })
      .filter((item): item is NonNullable<typeof item> => item !== null);
  }, [profile]);

  const resolvedOrigen: 'NFC' | 'QR' | 'ENLACE' = useMemo(() => {
    if (origenParam === 'NFC' || origenParam === 'QR' || origenParam === 'ENLACE') {
      return origenParam;
    }
    return uid ? 'NFC' : 'ENLACE';
  }, [origenParam, uid]);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!profile) return;

    setSubmitError(null);
    if (!nombre.trim()) {
      setSubmitError('Por favor ingresa tu nombre.');
      return;
    }
    if (!consentimientoAceptado) {
      setSubmitError('Debes aceptar el consentimiento para enviar tus datos.');
      return;
    }

    const consentimientoTexto = (profile.consentimiento_texto || FALLBACK_CONSENT_TEXT).trim();
    setSubmitting(true);
    try {
      const response = await submitPublicLead(
        profile.slug,
        {
          nombre: nombre.trim(),
          apellido: apellido.trim(),
          empresa_nombre: empresaNombre.trim(),
          email: email.trim(),
          telefono: telefono.trim(),
          mensaje: mensaje.trim(),
          origen: resolvedOrigen,
          uid: uid ?? '',
          consentimiento_aceptado: true,
          consentimiento_texto: consentimientoTexto,
          website,
        },
        uid,
        resolvedOrigen,
      );
      setSubmitSuccess(response.mensaje || 'Gracias, tus datos han sido enviados.');
      setNombre('');
      setApellido('');
      setEmpresaNombre('');
      setEmail('');
      setTelefono('');
      setMensaje('');
      setWebsite('');
      setConsentimientoAceptado(false);
    } catch (err) {
      setSubmitError(mensajeDeError(err, 'No se pudieron enviar tus datos.'));
    } finally {
      setSubmitting(false);
    }
  }

  if (loading) {
    return (
      <Box
        sx={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 2,
          bgcolor: '#f8fafc',
          px: 2,
        }}
      >
        <CircularProgress />
        <Typography variant="body2" color="text.secondary">
          Cargando tarjeta digital…
        </Typography>
      </Box>
    );
  }

  if (notFound) {
    return (
      <Box sx={{ minHeight: '100vh', bgcolor: '#f8fafc', py: 6, px: 2 }}>
        <Container maxWidth="xs">
          <Card sx={{ borderRadius: 3, textAlign: 'center', p: 2 }}>
            <CardContent>
              <Typography variant="h5" fontWeight={700} gutterBottom>
                Perfil no disponible
              </Typography>
              <Typography variant="body2" color="text.secondary">
                Esta tarjeta digital no existe, fue desactivada o el enlace ya no es válido.
              </Typography>
            </CardContent>
          </Card>
        </Container>
      </Box>
    );
  }

  if (loadError || !profile) {
    return (
      <Box sx={{ minHeight: '100vh', bgcolor: '#f8fafc', py: 6, px: 2 }}>
        <Container maxWidth="xs">
          <Alert severity="error">{loadError || 'No se pudo cargar la tarjeta digital.'}</Alert>
        </Container>
      </Box>
    );
  }

  const palette = getTemaPalette(profile.tema);
  const vcardUrl = getPublicVCardUrl(profile.slug, uid);
  const telHref = buildHrefSeguro({ tipo: 'telefono', valor: profile.telefono_publico });
  const emailHref = buildHrefSeguro({ tipo: 'correo', valor: profile.email_publico });
  const consentimientoTexto = profile.consentimiento_texto || FALLBACK_CONSENT_TEXT;

  return (
    <Box sx={{ minHeight: '100vh', bgcolor: palette.pageBg, py: { xs: 2, sm: 4 }, px: 1.5 }}>
      <Container maxWidth="xs">
        <Stack spacing={2.5}>
          <Card sx={{ borderRadius: 3, overflow: 'hidden', boxShadow: 3 }}>
            <Box
              sx={{
                background: palette.headerBg,
                color: palette.headerText,
                px: 3,
                py: 3.5,
                textAlign: 'center',
              }}
            >
              <Avatar
                sx={{
                  width: 76,
                  height: 76,
                  mx: 'auto',
                  mb: 1.5,
                  bgcolor: 'rgba(255, 255, 255, 0.22)',
                  color: palette.headerText,
                  fontSize: 26,
                  fontWeight: 700,
                }}
              >
                {getIniciales(profile.nombre_publico)}
              </Avatar>
              <Typography component="h1" variant="h5" fontWeight={700}>
                {profile.nombre_publico}
              </Typography>
              {profile.cargo && (
                <Typography variant="body2" sx={{ opacity: 0.92, mt: 0.5 }}>
                  {profile.cargo}
                </Typography>
              )}
              {profile.empresa_nombre && (
                <Chip
                  icon={<BusinessOutlined sx={{ color: 'inherit !important' }} />}
                  label={profile.empresa_nombre}
                  size="small"
                  sx={{
                    mt: 1.5,
                    bgcolor: palette.chipBg,
                    color: palette.headerText,
                    fontWeight: 500,
                  }}
                />
              )}
            </Box>

            <CardContent sx={{ p: 3 }}>
              <Stack spacing={2}>
                {profile.bio && (
                  <Typography variant="body2" color="text.secondary" sx={{ whiteSpace: 'pre-line' }}>
                    {profile.bio}
                  </Typography>
                )}

                {(telHref || emailHref) && (
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
                    {telHref && (
                      <Chip
                        component="a"
                        href={telHref}
                        clickable
                        icon={<PhoneOutlined />}
                        label={profile.telefono_publico}
                        variant="outlined"
                      />
                    )}
                    {emailHref && (
                      <Chip
                        component="a"
                        href={emailHref}
                        clickable
                        icon={<EmailOutlined />}
                        label={profile.email_publico}
                        variant="outlined"
                      />
                    )}
                  </Stack>
                )}

                <Button
                  component="a"
                  href={vcardUrl}
                  download={`${profile.slug}.vcf`}
                  variant="contained"
                  size="large"
                  fullWidth
                  startIcon={<DownloadOutlined />}
                >
                  Guardar contacto (.vcf)
                </Button>

                {safeButtons.length > 0 && (
                  <>
                    <Divider />
                    <Stack spacing={1.25}>
                      {safeButtons.map((boton) => (
                        <Button
                          key={boton.key}
                          component="a"
                          href={boton.href}
                          target={boton.isExternalHttp ? '_blank' : undefined}
                          rel={boton.isExternalHttp ? 'noopener noreferrer' : undefined}
                          variant="outlined"
                          fullWidth
                          endIcon={boton.isExternalHttp ? <OpenInNewOutlined fontSize="small" /> : undefined}
                          sx={{ justifyContent: 'space-between', textTransform: 'none', py: 1.1 }}
                        >
                          <span>{boton.etiqueta}</span>
                        </Button>
                      ))}
                    </Stack>
                  </>
                )}
              </Stack>
            </CardContent>
          </Card>

          {profile.acepta_leads && (
            <Card sx={{ borderRadius: 3, boxShadow: 2 }}>
              <CardContent sx={{ p: 3 }}>
                <Stack direction="row" spacing={1} alignItems="center" mb={1}>
                  <ContactMailOutlined color="primary" />
                  <Typography variant="h6" fontWeight={700}>
                    Compartir tus datos
                  </Typography>
                </Stack>
                <Typography variant="body2" color="text.secondary" mb={2}>
                  Deja tus datos de contacto para que {profile.nombre_publico} pueda comunicarse contigo.
                </Typography>

                {submitSuccess && (
                  <Alert severity="success" sx={{ mb: 2 }}>
                    {submitSuccess}
                  </Alert>
                )}

                {submitError && (
                  <Alert severity="error" sx={{ mb: 2 }}>
                    {submitError}
                  </Alert>
                )}

                <Box component="form" onSubmit={handleSubmit} noValidate>
                  <Stack spacing={1.75}>
                    <TextField
                      label="Nombre"
                      required
                      fullWidth
                      size="small"
                      value={nombre}
                      onChange={(e) => setNombre(e.target.value)}
                    />
                    <TextField
                      label="Apellido"
                      fullWidth
                      size="small"
                      value={apellido}
                      onChange={(e) => setApellido(e.target.value)}
                    />
                    <TextField
                      label="Empresa"
                      fullWidth
                      size="small"
                      value={empresaNombre}
                      onChange={(e) => setEmpresaNombre(e.target.value)}
                    />
                    <TextField
                      label="Correo electrónico"
                      type="email"
                      fullWidth
                      size="small"
                      value={email}
                      onChange={(e) => setEmail(e.target.value)}
                    />
                    <TextField
                      label="Teléfono"
                      type="tel"
                      fullWidth
                      size="small"
                      value={telefono}
                      onChange={(e) => setTelefono(e.target.value)}
                    />
                    <TextField
                      label="Mensaje"
                      multiline
                      minRows={2}
                      fullWidth
                      size="small"
                      value={mensaje}
                      onChange={(e) => setMensaje(e.target.value)}
                    />

                    {/* Campo honeypot oculto para filtrar envíos automatizados */}
                    <div
                      aria-hidden="true"
                      style={{
                        position: 'absolute',
                        left: '-9999px',
                        width: '1px',
                        height: '1px',
                        overflow: 'hidden',
                      }}
                    >
                      <label htmlFor="connect-lead-website">Website</label>
                      <input
                        id="connect-lead-website"
                        type="text"
                        name="website"
                        tabIndex={-1}
                        autoComplete="off"
                        value={website}
                        onChange={(e) => setWebsite(e.target.value)}
                      />
                    </div>

                    <Box
                      sx={{
                        p: 1.5,
                        borderRadius: 2,
                        bgcolor: 'action.hover',
                      }}
                    >
                      <Typography variant="caption" color="text.secondary" display="block" mb={0.5}>
                        {consentimientoTexto}
                      </Typography>
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={consentimientoAceptado}
                            onChange={(e) => setConsentimientoAceptado(e.target.checked)}
                            inputProps={{ 'aria-label': 'Acepto el consentimiento de contacto' }}
                          />
                        }
                        label={
                          <Typography variant="body2">
                            Acepto el tratamiento de mis datos para recibir respuesta.
                          </Typography>
                        }
                      />
                    </Box>

                    <Button
                      type="submit"
                      variant="contained"
                      size="large"
                      fullWidth
                      startIcon={<SendOutlined />}
                      disabled={submitting || !consentimientoAceptado || !nombre.trim()}
                    >
                      {submitting ? 'Enviando…' : 'Enviar mis datos'}
                    </Button>
                  </Stack>
                </Box>
              </CardContent>
            </Card>
          )}
        </Stack>
      </Container>
    </Box>
  );
}
