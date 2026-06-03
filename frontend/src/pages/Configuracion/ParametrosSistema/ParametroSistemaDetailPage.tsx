import { useState, useEffect } from 'react';
import type { FormEvent } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { Alert, Box, Button, MenuItem, Stack, TextField } from '@mui/material';
import { PageHeader } from '../../../components/ui';
import { get, post, patch } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';

const TIPOS_DATO = ['STRING', 'INTEGER', 'DECIMAL', 'BOOLEAN', 'JSON', 'DATE'];

export default function ParametroSistemaDetailPage() {
  const { id_parametro } = useParams<{ id_parametro: string }>();
  const navigate = useNavigate();
  const isNew = !id_parametro || id_parametro === 'new';

  const [form, setForm] = useState({
    codigo_parametro: '',
    nombre_parametro: '',
    valor_parametro: '',
    tipo_dato: 'STRING',
    descripcion: '',
  });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const { data: parametroExistente } = useQuery({
    queryKey: [`/configuracion_motor/parametros-sistema/${id_parametro}/`],
    queryFn: () => get(`/configuracion_motor/parametros-sistema/${id_parametro}/`),
    enabled: !isNew,
  });

  useEffect(() => {
    if (parametroExistente) {
      const p = parametroExistente as Partial<typeof form>;
      setForm((f) => ({ ...f, ...p }));
    }
  }, [parametroExistente]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (isNew) {
        await post('/configuracion_motor/parametros-sistema/', form);
      } else {
        await patch(`/configuracion_motor/parametros-sistema/${id_parametro}/`, form);
      }
      setSuccess(true);
      setTimeout(() => navigate('/configuracion/parametros-sistema'), 800);
    } catch {
      setError('Error al guardar el parámetro.');
    } finally {
      setLoading(false);
    }
  };

  const set = (field: string, value: string) => setForm((f) => ({ ...f, [field]: value }));

  return (
    <PageLayout maxWidth={640}>
      <PageHeader title={isNew ? 'Nuevo Parámetro' : 'Editar Parámetro'} />
      <Box component="form" onSubmit={handleSubmit}>
        <Stack spacing={2}>
          {success && <Alert severity="success">Guardado correctamente.</Alert>}
          {error && <Alert severity="error">{error}</Alert>}
          <TextField label="Código del parámetro" value={form.codigo_parametro} onChange={(e) => set('codigo_parametro', e.target.value)} required fullWidth />
          <TextField label="Nombre del parámetro" value={form.nombre_parametro} onChange={(e) => set('nombre_parametro', e.target.value)} required fullWidth />
          <TextField label="Valor del parámetro" value={form.valor_parametro} onChange={(e) => set('valor_parametro', e.target.value)} fullWidth multiline minRows={3} />
          <TextField select label="Tipo de dato" value={form.tipo_dato} onChange={(e) => set('tipo_dato', e.target.value)} fullWidth>
            {TIPOS_DATO.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
          </TextField>
          <TextField label="Descripción" value={form.descripcion} onChange={(e) => set('descripcion', e.target.value)} fullWidth multiline minRows={2} />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={() => navigate('/configuracion/parametros-sistema')}>Cancelar</Button>
            <Button type="submit" variant="contained" disabled={loading}>
              {loading ? 'Guardando…' : 'Guardar'}
            </Button>
          </Stack>
        </Stack>
      </Box>
    </PageLayout>
  );
}
