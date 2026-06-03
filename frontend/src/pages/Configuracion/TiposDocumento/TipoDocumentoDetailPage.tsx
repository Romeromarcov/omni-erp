import { useState, useEffect } from 'react';
import type { FormEvent } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Checkbox,
  FormControlLabel,
  MenuItem,
  Stack,
  TextField,
} from '@mui/material';
import { PageHeader } from '../../../components/ui';
import { get, post, patch } from '../../../services/api';
import PageLayout from '../../../components/PageLayout';

type TipoDocumentoForm = {
  codigo: string;
  nombre: string;
  descripcion: string;
  modulo_origen: string;
  es_transaccional: boolean;
  afecta_inventario: boolean;
  afecta_contabilidad: boolean;
  prefijo_correlativo: string;
  longitud_correlativo: number;
};

const MODULOS = ['VENTAS', 'COMPRAS', 'INVENTARIO', 'FINANZAS', 'CONTABILIDAD', 'RRHH', 'GENERAL'];

export default function TipoDocumentoDetailPage() {
  const { id_tipo_documento } = useParams<{ id_tipo_documento: string }>();
  const navigate = useNavigate();
  const isNew = !id_tipo_documento || id_tipo_documento === 'new';

  const [form, setForm] = useState<TipoDocumentoForm>({
    codigo: '',
    nombre: '',
    descripcion: '',
    modulo_origen: 'GENERAL',
    es_transaccional: false,
    afecta_inventario: false,
    afecta_contabilidad: false,
    prefijo_correlativo: '',
    longitud_correlativo: 8,
  });
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState(false);
  const [loading, setLoading] = useState(false);

  const { data: tipoExistente } = useQuery({
    queryKey: [`/configuracion_motor/tipos-documento/${id_tipo_documento}/`],
    queryFn: () => get(`/configuracion_motor/tipos-documento/${id_tipo_documento}/`),
    enabled: !isNew,
  });

  useEffect(() => {
    if (tipoExistente) {
      const td = tipoExistente as Partial<TipoDocumentoForm>;
      setForm((f) => ({ ...f, ...td }));
    }
  }, [tipoExistente]);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      if (isNew) {
        await post('/configuracion_motor/tipos-documento/', form);
      } else {
        await patch(`/configuracion_motor/tipos-documento/${id_tipo_documento}/`, form);
      }
      setSuccess(true);
      setTimeout(() => navigate('/configuracion/tipos-documento'), 800);
    } catch {
      setError('Error al guardar el tipo de documento.');
    } finally {
      setLoading(false);
    }
  };

  const set = <K extends keyof TipoDocumentoForm>(field: K, value: TipoDocumentoForm[K]) =>
    setForm((f) => ({ ...f, [field]: value }));

  return (
    <PageLayout maxWidth={640}>
      <PageHeader title={isNew ? 'Nuevo Tipo de Documento' : 'Editar Tipo de Documento'} />
      <Box component="form" onSubmit={handleSubmit}>
        <Stack spacing={2}>
          {success && <Alert severity="success">Guardado correctamente.</Alert>}
          {error && <Alert severity="error">{error}</Alert>}
          <TextField label="Código" value={form.codigo} onChange={(e) => set('codigo', e.target.value)} required fullWidth />
          <TextField label="Nombre" value={form.nombre} onChange={(e) => set('nombre', e.target.value)} required fullWidth />
          <TextField label="Descripción" value={form.descripcion} onChange={(e) => set('descripcion', e.target.value)} fullWidth multiline minRows={3} />
          <TextField select label="Módulo de origen" value={form.modulo_origen} onChange={(e) => set('modulo_origen', e.target.value)} fullWidth>
            {MODULOS.map((m) => <MenuItem key={m} value={m}>{m}</MenuItem>)}
          </TextField>
          <FormControlLabel
            control={<Checkbox checked={form.es_transaccional} onChange={(e) => set('es_transaccional', e.target.checked)} />}
            label="Es transaccional"
          />
          <FormControlLabel
            control={<Checkbox checked={form.afecta_inventario} onChange={(e) => set('afecta_inventario', e.target.checked)} />}
            label="Afecta inventario"
          />
          <FormControlLabel
            control={<Checkbox checked={form.afecta_contabilidad} onChange={(e) => set('afecta_contabilidad', e.target.checked)} />}
            label="Afecta contabilidad"
          />
          <TextField label="Prefijo correlativo" value={form.prefijo_correlativo} onChange={(e) => set('prefijo_correlativo', e.target.value)} fullWidth />
          <TextField
            type="number"
            label="Longitud correlativo"
            value={form.longitud_correlativo}
            onChange={(e) => set('longitud_correlativo', parseInt(e.target.value) || 0)}
            fullWidth
          />
          <Stack direction="row" spacing={1} justifyContent="flex-end">
            <Button variant="outlined" onClick={() => navigate('/configuracion/tipos-documento')}>Cancelar</Button>
            <Button type="submit" variant="contained" disabled={loading}>
              {loading ? 'Guardando…' : 'Guardar'}
            </Button>
          </Stack>
        </Stack>
      </Box>
    </PageLayout>
  );
}
