import { useState, useEffect } from 'react';
import type { FormEvent } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, Checkbox, FormControlLabel, Stack, TextField } from '@mui/material';
import { PageHeader } from '../../../components/ui';
import { get, post, patch } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';

export default function CatalogoValorDetailPage() {
  const { id_catalogo_valor } = useParams<{ id_catalogo_valor: string }>();
  const navigate = useNavigate();
  const isNew = !id_catalogo_valor || id_catalogo_valor === 'new';

  const [form, setForm] = useState({
    codigo_catalogo: '',
    valor: '',
    descripcion: '',
    orden: 0,
    activo: true,
  });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const { data: catalogoExistente } = useQuery({
    queryKey: [`/configuracion_motor/catalogos-valor/${id_catalogo_valor}/`],
    queryFn: () => get(`/configuracion_motor/catalogos-valor/${id_catalogo_valor}/`),
    enabled: !isNew,
  });

  useEffect(() => {
    if (catalogoExistente) {
      const c = catalogoExistente as Partial<typeof form>;
      setForm((f) => ({ ...f, ...c }));
    }
  }, [catalogoExistente]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (isNew) {
        await post('/configuracion_motor/catalogos-valor/', form);
      } else {
        await patch(`/configuracion_motor/catalogos-valor/${id_catalogo_valor}/`, form);
      }
      setSuccess(true);
      setTimeout(() => navigate('/configuracion/catalogos-valor'), 800);
    } catch {
      setError('Error al guardar el valor de catálogo.');
    } finally {
      setLoading(false);
    }
  };

  const set = <K extends keyof typeof form>(field: K, value: (typeof form)[K]) =>
    setForm((f) => ({ ...f, [field]: value }));

  return (
    <PageLayout maxWidth={640}>
      <PageHeader title={isNew ? 'Nuevo Valor de Catálogo' : 'Editar Valor de Catálogo'} />
      <Box component="form" onSubmit={handleSubmit}>
        <Stack spacing={2}>
          {success && <Alert severity="success">Guardado correctamente.</Alert>}
          {error && <Alert severity="error">{error}</Alert>}
          <TextField label="Código del catálogo" value={form.codigo_catalogo} onChange={(e) => set('codigo_catalogo', e.target.value)} required fullWidth />
          <TextField label="Valor" value={form.valor} onChange={(e) => set('valor', e.target.value)} required fullWidth />
          <TextField label="Descripción" value={form.descripcion} onChange={(e) => set('descripcion', e.target.value)} fullWidth multiline minRows={2} />
          <TextField type="number" label="Orden" value={form.orden} onChange={(e) => set('orden', parseInt(e.target.value) || 0)} fullWidth />
          <FormControlLabel
            control={<Checkbox checked={form.activo} onChange={(e) => set('activo', e.target.checked)} />}
            label="Activo"
          />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={() => navigate('/configuracion/catalogos-valor')}>Cancelar</Button>
            <Button type="submit" variant="contained" disabled={loading}>
              {loading ? 'Guardando…' : 'Guardar'}
            </Button>
          </Stack>
        </Stack>
      </Box>
    </PageLayout>
  );
}
