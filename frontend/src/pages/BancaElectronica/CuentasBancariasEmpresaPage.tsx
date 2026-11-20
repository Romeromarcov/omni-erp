import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  Checkbox,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Typography,
} from '@mui/material';
import AddOutlined from '@mui/icons-material/AddOutlined';
import DownloadOutlined from '@mui/icons-material/DownloadOutlined';
import VerifiedUserOutlined from '@mui/icons-material/VerifiedUserOutlined';
import { PageContainer, PageHeader, DataTable, StatusChip } from '../../components/ui';
import type { Column } from '../../components/ui';
import {
  cuentasBancariasEmpresaService,
  lotesPagoBancarioService,
  validarCuentaVe,
  validarReferenciaBancaria,
  type CuentaBancariaEmpresa,
  type CuentaBancariaEmpresaPayload,
  type EstadoLotePago,
  type FormatoBancoVE,
  type LotePagoBancario,
  type TipoCuenta,
  type ValidarCuentaVeResponse,
  type ValidarReferenciaResponse,
} from '../../services/bancaElectronicaService';
import { fetchMonedas } from '../../services/monedas';
import { pagosService, type Pago } from '../../services/pagosService';
import { nominaService, type ProcesoNomina } from '../../services/nominaService';
import { bancaElectronicaKeys, finanzasKeys } from '../../lib/queryKeys';
import { parseDecimalStrict } from '../../lib/decimal';
import { getEmpresaId } from '../../utils/empresa';
import { mensajeDeError } from '../../utils/api';

const TIPOS_CUENTA: { value: TipoCuenta; label: string }[] = [
  { value: 'CORRIENTE', label: 'Corriente' },
  { value: 'AHORRO', label: 'Ahorro' },
  { value: 'CREDITO', label: 'Crédito' },
];

const FORMATOS_BANCO: { value: FormatoBancoVE; label: string }[] = [
  { value: 'BANESCO_TXT', label: 'Banesco TXT' },
  { value: 'MERCANTIL_TXT', label: 'Mercantil TXT' },
  { value: 'BDV_TXT', label: 'Banco de Venezuela TXT' },
  { value: 'GENERICO_CSV', label: 'Genérico CSV' },
];

interface FormState {
  nombre_banco: string;
  numero_cuenta: string;
  tipo_cuenta: TipoCuenta;
  id_moneda: string;
  saldo_actual: string;
  activo: boolean;
}

const FORM_VACIO: FormState = {
  nombre_banco: '',
  numero_cuenta: '',
  tipo_cuenta: 'CORRIENTE',
  id_moneda: '',
  saldo_actual: '0.00',
  activo: true,
};

function labelTipoCuenta(tipo: TipoCuenta): string {
  if (tipo === 'AHORRO') return 'Ahorro';
  if (tipo === 'CREDITO') return 'Crédito';
  return 'Corriente';
}

function colorEstadoLote(
  estado: EstadoLotePago,
): 'default' | 'primary' | 'info' | 'success' | 'error' | 'warning' {
  switch (estado) {
    case 'GENERADO':
      return 'info';
    case 'ENVIADO':
      return 'primary';
    case 'PROCESADO':
      return 'success';
    case 'ANULADO':
      return 'error';
    default:
      return 'default';
  }
}

function hoyIso(): string {
  return new Date().toISOString().slice(0, 10);
}

const CuentasBancariasEmpresaPage: React.FC = () => {
  const queryClient = useQueryClient();
  const empresaId = getEmpresaId() || '';
  const [tab, setTab] = useState(0);
  const [errorMsg, setErrorMsg] = useState('');
  const [infoMsg, setInfoMsg] = useState('');

  // ── Estado Tab 0: Cuentas Bancarias (maestro finanzas) ───────────────────
  const [dialogOpen, setDialogOpen] = useState(false);
  const [editando, setEditando] = useState<CuentaBancariaEmpresa | null>(null);
  const [form, setForm] = useState<FormState>(FORM_VACIO);

  // ── Estado Tab 1: Lotes de Pago VE ───────────────────────────────────────
  const [loteProvOpen, setLoteProvOpen] = useState(false);
  const [loteNomOpen, setLoteNomOpen] = useState(false);
  const [loteCuentaId, setLoteCuentaId] = useState('');
  const [loteFormato, setLoteFormato] = useState<FormatoBancoVE>('BANESCO_TXT');
  const [loteFechaValor, setLoteFechaValor] = useState(hoyIso);
  const [loteReferencia, setLoteReferencia] = useState('');
  const [pagosSeleccionados, setPagosSeleccionados] = useState<Set<string>>(() => new Set());
  const [overridesPagos, setOverridesPagos] = useState<Map<string, string>>(() => new Map());
  const [procesoNominaId, setProcesoNominaId] = useState('');
  const [cuentasEmpleadosJson, setCuentasEmpleadosJson] = useState('');

  // ── Estado Tab 2: Validador Bancario VE ──────────────────────────────────
  const [cuentaVeInput, setCuentaVeInput] = useState('');
  const [cuentaVeResult, setCuentaVeResult] = useState<ValidarCuentaVeResponse | null>(null);
  const [refCuentaId, setRefCuentaId] = useState('');
  const [refInput, setRefInput] = useState('');
  const [refResult, setRefResult] = useState<ValidarReferenciaResponse | null>(null);

  // ── Queries ──────────────────────────────────────────────────────────────
  const { data: cuentas = [], isLoading: loadingCuentas } = useQuery({
    queryKey: bancaElectronicaKeys.cuentas(empresaId),
    queryFn: () =>
      cuentasBancariasEmpresaService.getAll({ empresa: empresaId || undefined }),
  });

  const { data: monedas = [] } = useQuery({
    queryKey: finanzasKeys.monedas.all(),
    queryFn: () => fetchMonedas(),
  });

  const { data: lotes = [], isLoading: loadingLotes } = useQuery({
    queryKey: bancaElectronicaKeys.lotes(empresaId),
    queryFn: () => lotesPagoBancarioService.getAll({ empresa: empresaId || undefined }),
    enabled: tab === 1,
  });

  const { data: pagosEgreso = [] } = useQuery<Pago[]>({
    queryKey: ['finanzas', 'pagos', 'egreso', empresaId],
    queryFn: () =>
      pagosService.getPagos({
        tipo_operacion: 'EGRESO',
        id_empresa: empresaId || undefined,
      }),
    enabled: loteProvOpen,
  });

  const { data: procesosNominaRes } = useQuery({
    queryKey: ['nomina', 'procesos', 'list', empresaId],
    queryFn: () => nominaService.getProcesosPaginated(),
    enabled: loteNomOpen,
  });

  const procesosListos: ProcesoNomina[] = (procesosNominaRes?.results ?? []).filter(
    (p: ProcesoNomina) => p.estado === 'COMPLETADO' || p.estado === 'APROBADO',
  );

  const invalidateCuentas = () =>
    queryClient.invalidateQueries({ queryKey: bancaElectronicaKeys.cuentasAll() });
  const invalidateLotes = () =>
    queryClient.invalidateQueries({ queryKey: bancaElectronicaKeys.lotesAll() });

  // ── Mutaciones Cuentas Bancarias ─────────────────────────────────────────
  const abrirCrear = () => {
    setEditando(null);
    setForm(FORM_VACIO);
    setErrorMsg('');
    setDialogOpen(true);
  };

  const abrirEditar = (c: CuentaBancariaEmpresa) => {
    setEditando(c);
    setForm({
      nombre_banco: c.nombre_banco,
      numero_cuenta: c.numero_cuenta,
      tipo_cuenta: c.tipo_cuenta,
      id_moneda: c.id_moneda,
      saldo_actual: c.saldo_actual ?? '0.00',
      activo: c.activo ?? true,
    });
    setErrorMsg('');
    setDialogOpen(true);
  };

  const guardar = useMutation({
    mutationFn: (payload: CuentaBancariaEmpresaPayload) =>
      editando
        ? cuentasBancariasEmpresaService.update(editando.id_cuenta_bancaria, payload)
        : cuentasBancariasEmpresaService.create(payload),
    onSuccess: () => {
      setDialogOpen(false);
      invalidateCuentas();
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo guardar la cuenta.')),
  });

  const eliminar = useMutation({
    mutationFn: (id: string) => cuentasBancariasEmpresaService.remove(id),
    onSuccess: invalidateCuentas,
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo eliminar la cuenta.')),
  });

  const handleGuardar = () => {
    if (!form.nombre_banco.trim() || !form.numero_cuenta.trim() || !form.id_moneda) {
      setErrorMsg('Complete el banco, el número de cuenta y la moneda.');
      return;
    }
    const saldoInput = form.saldo_actual.trim() || '0';
    const saldoDec = parseDecimalStrict(saldoInput);
    if (!saldoDec) {
      setErrorMsg('El saldo actual debe ser un número decimal válido.');
      return;
    }
    const payload: CuentaBancariaEmpresaPayload = {
      id_empresa: editando ? editando.id_empresa || empresaId : empresaId,
      nombre_banco: form.nombre_banco.trim(),
      numero_cuenta: form.numero_cuenta.trim(),
      tipo_cuenta: form.tipo_cuenta,
      id_moneda: form.id_moneda,
      saldo_actual: saldoDec.toFixed(2),
      activo: form.activo,
    };
    guardar.mutate(payload);
  };

  const handleEliminar = (c: CuentaBancariaEmpresa) => {
    if (window.confirm(`¿Eliminar la cuenta "${c.nombre_banco} - ${c.numero_cuenta}"?`)) {
      eliminar.mutate(c.id_cuenta_bancaria);
    }
  };

  // ── Mutaciones Lotes de Pago VE ──────────────────────────────────────────
  const generarProvMut = useMutation({
    mutationFn: lotesPagoBancarioService.generarProveedores,
    onSuccess: (lote) => {
      setLoteProvOpen(false);
      setPagosSeleccionados(new Set());
      setOverridesPagos(new Map());
      setLoteReferencia('');
      setInfoMsg(`Lote de proveedores ${lote.referencia_lote} generado correctamente.`);
      invalidateLotes();
    },
    onError: (e: unknown) =>
      setErrorMsg(mensajeDeError(e, 'No se pudo generar el lote de proveedores.')),
  });

  const generarNomMut = useMutation({
    mutationFn: lotesPagoBancarioService.generarNomina,
    onSuccess: (lote) => {
      setLoteNomOpen(false);
      setProcesoNominaId('');
      setCuentasEmpleadosJson('');
      setLoteReferencia('');
      setInfoMsg(`Lote de nómina ${lote.referencia_lote} generado correctamente.`);
      invalidateLotes();
    },
    onError: (e: unknown) =>
      setErrorMsg(mensajeDeError(e, 'No se pudo generar el lote de nómina.')),
  });

  const transicionLoteMut = useMutation({
    mutationFn: ({ id, accion }: { id: string; accion: 'enviar' | 'procesar' | 'anular' }) => {
      if (accion === 'enviar') return lotesPagoBancarioService.marcarEnviado(id);
      if (accion === 'procesar') return lotesPagoBancarioService.marcarProcesado(id);
      return lotesPagoBancarioService.anular(id);
    },
    onSuccess: () => {
      invalidateLotes();
    },
    onError: (e: unknown) =>
      setErrorMsg(mensajeDeError(e, 'No se pudo actualizar el estado del lote.')),
  });

  const descargarLote = async (lote: LotePagoBancario) => {
    try {
      const blob = await lotesPagoBancarioService.descargar(lote.id_lote_pago);
      const objUrl = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = objUrl;
      a.download = lote.nombre_archivo || `lote_${lote.referencia_lote}.txt`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(objUrl);
    } catch (e: unknown) {
      setErrorMsg(mensajeDeError(e, 'No se pudo descargar el archivo del lote.'));
    }
  };

  const handleGenerarProveedores = () => {
    const ids = Array.from(pagosSeleccionados);
    if (!loteCuentaId || ids.length === 0 || !loteFechaValor) {
      setErrorMsg('Seleccione cuenta origen, fecha valor y al menos un pago EGRESO.');
      return;
    }
    const overrides = new Map<string, string>();
    for (const id of ids) {
      const val = overridesPagos.get(id)?.trim();
      if (val) overrides.set(id, val);
    }
    setErrorMsg('');
    generarProvMut.mutate({
      id_empresa: empresaId || undefined,
      id_cuenta_bancaria: loteCuentaId,
      pagos_ids: ids,
      formato_banco: loteFormato,
      fecha_valor: loteFechaValor,
      referencia_lote: loteReferencia.trim() || undefined,
      cuentas_destino_override: overrides.size > 0 ? Object.fromEntries(overrides) : undefined,
    });
  };

  const handleGenerarNomina = () => {
    if (!loteCuentaId || !procesoNominaId || !loteFechaValor) {
      setErrorMsg('Seleccione cuenta origen, proceso de nómina y fecha valor.');
      return;
    }
    const cuentasEmpleados = new Map<string, string>();
    for (const linea of cuentasEmpleadosJson.split('\n')) {
      const limpio = linea.trim();
      if (!limpio) continue;
      const sepIdx = limpio.indexOf(':');
      if (sepIdx > 0) {
        const key = limpio.slice(0, sepIdx).trim();
        const val = limpio.slice(sepIdx + 1).trim();
        if (key && val) cuentasEmpleados.set(key, val);
      }
    }
    setErrorMsg('');
    generarNomMut.mutate({
      id_empresa: empresaId || undefined,
      id_cuenta_bancaria: loteCuentaId,
      id_proceso_nomina: procesoNominaId,
      formato_banco: loteFormato,
      fecha_valor: loteFechaValor,
      referencia_lote: loteReferencia.trim() || undefined,
      cuentas_empleados:
        cuentasEmpleados.size > 0 ? Object.fromEntries(cuentasEmpleados) : undefined,
    });
  };

  // ── Mutaciones Validadores VE ────────────────────────────────────────────
  const validarVeMut = useMutation({
    mutationFn: (numero: string) => validarCuentaVe(numero),
    onSuccess: (res) => {
      setErrorMsg('');
      setCuentaVeResult(res);
    },
    onError: (e: unknown) => setErrorMsg(mensajeDeError(e, 'No se pudo validar la cuenta VE.')),
  });

  const validarRefMut = useMutation({
    mutationFn: validarReferenciaBancaria,
    onSuccess: (res) => {
      setErrorMsg('');
      setRefResult(res);
    },
    onError: (e: unknown) =>
      setErrorMsg(mensajeDeError(e, 'No se pudo validar la referencia bancaria.')),
  });

  // ── Helpers y Columnas ───────────────────────────────────────────────────
  const nombreMoneda = (id: string) => {
    const m = monedas.find((mo) => mo.id_moneda === id);
    return m ? m.codigo_iso : id;
  };

  const cuentaColumns: Column<CuentaBancariaEmpresa>[] = [
    { key: 'nombre_banco', header: 'Banco', render: (c) => c.nombre_banco },
    { key: 'numero_cuenta', header: 'Número', render: (c) => c.numero_cuenta },
    {
      key: 'tipo_cuenta',
      header: 'Tipo',
      render: (c) => labelTipoCuenta(c.tipo_cuenta),
    },
    {
      key: 'id_moneda',
      header: 'Moneda',
      render: (c) => c.moneda_codigo_iso || nombreMoneda(c.id_moneda),
    },
    { key: 'saldo_actual', header: 'Saldo', render: (c) => c.saldo_actual },
    { key: 'activo', header: 'Activa', render: (c) => <StatusChip value={c.activo ?? true} /> },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (c) => (
        <Stack direction="row" spacing={1}>
          <Button size="small" onClick={() => abrirEditar(c)}>
            Editar
          </Button>
          <Button
            size="small"
            color="error"
            disabled={eliminar.isPending}
            onClick={() => handleEliminar(c)}
          >
            Eliminar
          </Button>
        </Stack>
      ),
    },
  ];

  const loteColumns: Column<LotePagoBancario>[] = [
    { key: 'referencia_lote', header: 'Referencia', render: (l) => l.referencia_lote },
    { key: 'tipo_lote', header: 'Tipo', render: (l) => l.tipo_lote },
    { key: 'formato_banco', header: 'Formato', render: (l) => l.formato_banco },
    { key: 'fecha_valor', header: 'Fecha Valor', render: (l) => l.fecha_valor },
    { key: 'total_registros', header: 'Registros', render: (l) => String(l.total_registros) },
    { key: 'monto_total', header: 'Monto Total', render: (l) => l.monto_total },
    {
      key: 'estado',
      header: 'Estado',
      render: (l) => <Chip label={l.estado} size="small" color={colorEstadoLote(l.estado)} />,
    },
    {
      key: 'acciones',
      header: 'Acciones',
      render: (l) => (
        <Stack direction="row" spacing={1}>
          <Button
            size="small"
            startIcon={<DownloadOutlined />}
            onClick={() => void descargarLote(l)}
          >
            Descargar
          </Button>
          {l.estado === 'GENERADO' && (
            <Button
              size="small"
              onClick={() => transicionLoteMut.mutate({ id: l.id_lote_pago, accion: 'enviar' })}
            >
              Enviar
            </Button>
          )}
          {l.estado === 'ENVIADO' && (
            <Button
              size="small"
              color="success"
              onClick={() => transicionLoteMut.mutate({ id: l.id_lote_pago, accion: 'procesar' })}
            >
              Procesar
            </Button>
          )}
          {(l.estado === 'GENERADO' || l.estado === 'BORRADOR') && (
            <Button
              size="small"
              color="error"
              onClick={() => transicionLoteMut.mutate({ id: l.id_lote_pago, accion: 'anular' })}
            >
              Anular
            </Button>
          )}
        </Stack>
      ),
    },
  ];

  return (
    <PageContainer>
      <PageHeader
        title="Banca Electrónica"
        subtitle="Cuentas bancarias canónicas, lotes de pago VE y validación bancaria."
        actions={
          tab === 0 ? (
            <Button variant="contained" startIcon={<AddOutlined />} onClick={abrirCrear}>
              Nueva cuenta
            </Button>
          ) : tab === 1 ? (
            <Stack direction="row" spacing={1}>
              <Button
                variant="contained"
                startIcon={<AddOutlined />}
                onClick={() => {
                  setErrorMsg('');
                  setLoteCuentaId(cuentas[0]?.id_cuenta_bancaria ?? '');
                  setLoteProvOpen(true);
                }}
              >
                Generar Lote Proveedores
              </Button>
              <Button
                variant="outlined"
                startIcon={<AddOutlined />}
                onClick={() => {
                  setErrorMsg('');
                  setLoteCuentaId(cuentas[0]?.id_cuenta_bancaria ?? '');
                  setLoteNomOpen(true);
                }}
              >
                Generar Lote Nómina
              </Button>
            </Stack>
          ) : null
        }
      />

      {errorMsg && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setErrorMsg('')}>
          {errorMsg}
        </Alert>
      )}
      {infoMsg && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => setInfoMsg('')}>
          {infoMsg}
        </Alert>
      )}

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 2 }}>
        <Tabs value={tab} onChange={(_, v: number) => setTab(v)}>
          <Tab label="Cuentas Bancarias" />
          <Tab label="Lotes de Pago VE" />
          <Tab label="Validador Bancario" />
        </Tabs>
      </Box>

      {tab === 0 && (
        <DataTable
          columns={cuentaColumns}
          rows={cuentas}
          getRowKey={(c) => c.id_cuenta_bancaria}
          loading={loadingCuentas}
          emptyMessage="Sin cuentas bancarias. Crea la primera."
        />
      )}

      {tab === 1 && (
        <DataTable
          columns={loteColumns}
          rows={lotes}
          getRowKey={(l) => l.id_lote_pago}
          loading={loadingLotes}
          emptyMessage="Sin lotes de pago bancario generados."
        />
      )}

      {tab === 2 && (
        <Stack spacing={3}>
          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Validador de Cuenta Bancaria VE (SUDEBAN 20 dígitos)
              </Typography>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="flex-start">
                <TextField
                  label="Número de cuenta VE"
                  value={cuentaVeInput}
                  onChange={(e) => setCuentaVeInput(e.target.value)}
                  placeholder="0134-0001-01-0123456789"
                  fullWidth
                />
                <Button
                  variant="contained"
                  startIcon={<VerifiedUserOutlined />}
                  disabled={validarVeMut.isPending}
                  onClick={() => validarVeMut.mutate(cuentaVeInput)}
                >
                  Validar Cuenta VE
                </Button>
              </Stack>
              {cuentaVeResult && (
                <Alert severity={cuentaVeResult.valida ? 'success' : 'error'} sx={{ mt: 2 }}>
                  {cuentaVeResult.valida
                    ? `Cuenta válida · ${cuentaVeResult.banco_nombre} (${cuentaVeResult.codigo_banco}) · ${cuentaVeResult.numero_normalizado}`
                    : `Cuenta inválida: ${cuentaVeResult.errores.join(' ')}`}
                </Alert>
              )}
            </CardContent>
          </Card>

          <Card variant="outlined">
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Detector de Referencias Bancarias Duplicadas
              </Typography>
              <Stack spacing={2}>
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                  <TextField
                    select
                    label="Cuenta bancaria (opcional)"
                    value={refCuentaId}
                    onChange={(e) => setRefCuentaId(e.target.value)}
                    fullWidth
                  >
                    <MenuItem value="">Todas las cuentas de la empresa</MenuItem>
                    {cuentas.map((c) => (
                      <MenuItem key={c.id_cuenta_bancaria} value={c.id_cuenta_bancaria}>
                        {c.nombre_banco} — {c.numero_cuenta}
                      </MenuItem>
                    ))}
                  </TextField>
                  <TextField
                    label="Referencia bancaria"
                    value={refInput}
                    onChange={(e) => setRefInput(e.target.value)}
                    fullWidth
                  />
                </Stack>
                <Box>
                  <Button
                    variant="contained"
                    disabled={validarRefMut.isPending || !refInput.trim()}
                    onClick={() =>
                      validarRefMut.mutate({
                        id_empresa: empresaId || undefined,
                        id_cuenta_bancaria: refCuentaId || undefined,
                        referencia: refInput.trim(),
                      })
                    }
                  >
                    Verificar Referencia
                  </Button>
                </Box>
                {refResult && (
                  <Alert severity={refResult.duplicada ? 'warning' : 'success'}>
                    {refResult.duplicada
                      ? `Referencia ${refResult.referencia_normalizada} duplicada (${refResult.coincidencias.length} coincidencia(s)): ${refResult.coincidencias.map((c) => `${c.origen}: ${c.detalle}`).join(' | ')}`
                      : `Referencia ${refResult.referencia_normalizada} disponible (sin duplicados).`}
                  </Alert>
                )}
              </Stack>
            </CardContent>
          </Card>
        </Stack>
      )}

      {/* Diálogo Crear/Editar Cuenta Bancaria Canónica */}
      <Dialog open={dialogOpen} onClose={() => setDialogOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>{editando ? 'Editar cuenta' : 'Nueva cuenta'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Banco"
              value={form.nombre_banco}
              onChange={(e) => setForm((f) => ({ ...f, nombre_banco: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              label="Número de cuenta"
              value={form.numero_cuenta}
              onChange={(e) => setForm((f) => ({ ...f, numero_cuenta: e.target.value }))}
              required
              fullWidth
            />
            <TextField
              select
              label="Tipo de cuenta"
              value={form.tipo_cuenta}
              onChange={(e) =>
                setForm((f) => ({ ...f, tipo_cuenta: e.target.value as TipoCuenta }))
              }
              fullWidth
            >
              {TIPOS_CUENTA.map((t) => (
                <MenuItem key={t.value} value={t.value}>
                  {t.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Moneda"
              value={form.id_moneda}
              onChange={(e) => setForm((f) => ({ ...f, id_moneda: e.target.value }))}
              required
              fullWidth
            >
              {monedas.map((m) => (
                <MenuItem key={m.id_moneda} value={m.id_moneda}>
                  {m.codigo_iso} — {m.nombre}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Saldo actual"
              value={form.saldo_actual}
              onChange={(e) => setForm((f) => ({ ...f, saldo_actual: e.target.value }))}
              inputMode="decimal"
              fullWidth
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={form.activo}
                  onChange={(e) => setForm((f) => ({ ...f, activo: e.target.checked }))}
                />
              }
              label="Activa"
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogOpen(false)}>Cancelar</Button>
          <Button variant="contained" onClick={handleGuardar} disabled={guardar.isPending}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>

      {/* Diálogo Generar Lote Proveedores */}
      <Dialog open={loteProvOpen} onClose={() => setLoteProvOpen(false)} fullWidth maxWidth="md">
        <DialogTitle>Generar Lote de Pago a Proveedores</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Cuenta origen"
              value={loteCuentaId}
              onChange={(e) => setLoteCuentaId(e.target.value)}
              fullWidth
            >
              {cuentas.map((c) => (
                <MenuItem key={c.id_cuenta_bancaria} value={c.id_cuenta_bancaria}>
                  {c.nombre_banco} — {c.numero_cuenta}
                </MenuItem>
              ))}
            </TextField>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
              <TextField
                select
                label="Formato bancario"
                value={loteFormato}
                onChange={(e) => setLoteFormato(e.target.value as FormatoBancoVE)}
                fullWidth
              >
                {FORMATOS_BANCO.map((f) => (
                  <MenuItem key={f.value} value={f.value}>
                    {f.label}
                  </MenuItem>
                ))}
              </TextField>
              <TextField
                label="Fecha valor"
                type="date"
                value={loteFechaValor}
                onChange={(e) => setLoteFechaValor(e.target.value)}
                slotProps={{ inputLabel: { shrink: true } }}
                fullWidth
              />
              <TextField
                label="Referencia lote (opcional)"
                value={loteReferencia}
                onChange={(e) => setLoteReferencia(e.target.value)}
                fullWidth
              />
            </Stack>
            <Typography variant="subtitle2">Pagos EGRESO disponibles</Typography>
            <Stack spacing={1} sx={{ maxHeight: 240, overflowY: 'auto' }}>
              {pagosEgreso.length === 0 ? (
                <Typography variant="body2" color="text.secondary">
                  Sin pagos EGRESO disponibles.
                </Typography>
              ) : (
                pagosEgreso.map((p) => {
                  const pid = p.id_pago || '';
                  if (!pid) return null;
                  const checked = pagosSeleccionados.has(pid);
                  return (
                    <Stack key={pid} direction="row" spacing={1} alignItems="center">
                      <FormControlLabel
                        control={
                          <Checkbox
                            checked={checked}
                            onChange={(e) =>
                              setPagosSeleccionados((prev) => {
                                const next = new Set(prev);
                                if (e.target.checked) next.add(pid);
                                else next.delete(pid);
                                return next;
                              })
                            }
                          />
                        }
                        label={`${p.referencia || pid.slice(0, 8)} — ${p.monto} ${p.moneda_codigo || ''}`}
                      />
                      {checked && (
                        <TextField
                          size="small"
                          label="Cuenta destino override"
                          value={overridesPagos.get(pid) ?? ''}
                          onChange={(e) =>
                            setOverridesPagos((prev) => {
                              const next = new Map(prev);
                              next.set(pid, e.target.value);
                              return next;
                            })
                          }
                        />
                      )}
                    </Stack>
                  );
                })
              )}
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLoteProvOpen(false)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={handleGenerarProveedores}
            disabled={generarProvMut.isPending}
          >
            Generar Lote
          </Button>
        </DialogActions>
      </Dialog>

      {/* Diálogo Generar Lote Nómina */}
      <Dialog open={loteNomOpen} onClose={() => setLoteNomOpen(false)} fullWidth maxWidth="sm">
        <DialogTitle>Generar Lote de Pago de Nómina</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              select
              label="Cuenta origen"
              value={loteCuentaId}
              onChange={(e) => setLoteCuentaId(e.target.value)}
              fullWidth
            >
              {cuentas.map((c) => (
                <MenuItem key={c.id_cuenta_bancaria} value={c.id_cuenta_bancaria}>
                  {c.nombre_banco} — {c.numero_cuenta}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Proceso de nómina"
              value={procesoNominaId}
              onChange={(e) => setProcesoNominaId(e.target.value)}
              fullWidth
            >
              {procesosListos.map((pr) => (
                <MenuItem key={pr.id_proceso_nomina} value={pr.id_proceso_nomina}>
                  {pr.numero_proceso} ({pr.estado}) — {pr.total_neto}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              select
              label="Formato bancario"
              value={loteFormato}
              onChange={(e) => setLoteFormato(e.target.value as FormatoBancoVE)}
              fullWidth
            >
              {FORMATOS_BANCO.map((f) => (
                <MenuItem key={f.value} value={f.value}>
                  {f.label}
                </MenuItem>
              ))}
            </TextField>
            <TextField
              label="Fecha valor"
              type="date"
              value={loteFechaValor}
              onChange={(e) => setLoteFechaValor(e.target.value)}
              slotProps={{ inputLabel: { shrink: true } }}
              fullWidth
            />
            <TextField
              label="Referencia lote (opcional)"
              value={loteReferencia}
              onChange={(e) => setLoteReferencia(e.target.value)}
              fullWidth
            />
            <TextField
              label="Cuentas empleados override (id_empleado:numero_cuenta por línea)"
              value={cuentasEmpleadosJson}
              onChange={(e) => setCuentasEmpleadosJson(e.target.value)}
              multiline
              minRows={2}
              fullWidth
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setLoteNomOpen(false)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={handleGenerarNomina}
            disabled={generarNomMut.isPending}
          >
            Generar Lote
          </Button>
        </DialogActions>
      </Dialog>
    </PageContainer>
  );
};

export default CuentasBancariasEmpresaPage;
