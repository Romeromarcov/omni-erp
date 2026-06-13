/**
 * Base hook for all sales document forms (Cotizacion, Pedido, NotaVenta, FacturaFiscal).
 *
 * FE-CRIT-1: migrado a react-hook-form. El hook crea (o recibe) una instancia de
 * `useForm` tipada por el esquema zod del documento y expone sus primitivas
 * (control, register, handleSubmit, formState, reset, setValue, watch) junto con
 * un `useFieldArray` para `detalles`. El resto de estado asíncrono compartido
 * (productos, vendedores, sesión, empresas, sucursales, clientes similares) y los
 * helpers de cliente se mantienen como antes.
 *
 * `clienteManual`, `detalleForm`, `descuentoGeneral` y `pagos` siguen siendo
 * estado local del hook: NO son campos enviados directamente del formulario, sino
 * estado de UI auxiliar (staging de línea de producto, datos para autocrear el
 * cliente, descuento general y pagos del modal).
 */
import { useState, useEffect, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  useForm,
  useFieldArray,
  type FieldValues,
  type DefaultValues,
  type Path,
  type Resolver,
} from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import type { ZodTypeAny } from 'zod';
import { get } from '../services/api';
import { fetchProductos } from '../services/productosService';
import { buscarClientes, crearClienteConEmpresa, buscarClientesSimilares } from '../services/clientesService';
import { fetchUsuarios, type Usuario } from '../services/users';
import { getEmpresaId } from '../utils/empresa';
import { getSesionActiva, type SesionCaja } from '../services/sesionService';
import type { Producto } from '../services/productosService';
import type { Cliente } from '../services/clientesService';
import type { Pago } from '../components/Pedidos/ModalPago';

export interface CajaUsuario {
  es_predeterminada?: boolean;
  caja?: { id_caja: string };
  caja_nombre?: string;
  caja_moneda?: string;
}

export interface ClienteManual {
  razon_social: string;
  rif: string;
  telefono: string;
  direccion?: string;
  correo?: string;
  codigo_cliente?: string;
}

const CLIENTE_MANUAL_KEYS = [
  'razon_social',
  'rif',
  'telefono',
  'direccion',
  'correo',
  'codigo_cliente',
] as const satisfies readonly (keyof ClienteManual)[];

const isClienteManualKey = (name: string): name is keyof ClienteManual =>
  (CLIENTE_MANUAL_KEYS as readonly string[]).includes(name);

export interface DetalleDocumentoForm {
  id_producto: string;
  cantidad: string;
  precio_unitario: string;
  descuento_porcentaje?: string;
  sku?: string;
  producto?: string;
  comentarios?: string;
}

const emptyDetalleForm = (): DetalleDocumentoForm => ({
  id_producto: '', cantidad: '', precio_unitario: '', descuento_porcentaje: '', sku: '', producto: '', comentarios: '',
});

interface UseDocumentoVentaBaseOptions<TForm extends FieldValues> {
  /** Esquema zod del documento (se usa como resolver de react-hook-form). */
  schema: ZodTypeAny;
  /** Valores iniciales del formulario. */
  defaultValues: DefaultValues<TForm>;
  onCajaPredet?: (cajaId: string) => void;
  onSesionCargada?: (sesion: SesionCaja) => void;
  onVendedorPredet?: (userId: string) => void;
}

export const useDocumentoVentaBase = <TForm extends FieldValues>({
  schema,
  defaultValues,
  onCajaPredet,
  onSesionCargada,
  onVendedorPredet,
}: UseDocumentoVentaBaseOptions<TForm>) => {
  // ── react-hook-form ──────────────────────────────────────────────────────────
  const formMethods = useForm<TForm>({
    resolver: zodResolver(schema) as unknown as Resolver<TForm>,
    mode: 'onBlur',
    defaultValues,
  });
  const { control, register, handleSubmit, reset, setValue, watch, getValues, formState } = formMethods;
  const detallesArray = useFieldArray<TForm>({
    control,
    name: 'detalles' as never,
  });

  // empresaId reactivo: deriva de id_empresa del propio formulario.
  const empresaId = (watch('id_empresa' as Path<TForm>) as string | undefined) || '';

  // ── Estado auxiliar de UI (no es server-state) ───────────────────────────────
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const [detalleForm, setDetalleForm] = useState<DetalleDocumentoForm>(emptyDetalleForm());
  const [descuentoGeneral, setDescuentoGeneral] = useState('');
  const [pagos, setPagos] = useState<Pago[]>([]);
  const [clienteManual, setClienteManual] = useState<ClienteManual>({
    razon_social: '', rif: '', telefono: '', direccion: '', correo: '', codigo_cliente: '',
  });
  const [clientesSimilares, setClientesSimilares] = useState<Cliente[]>([]);

  const getFieldString = (obj: unknown, key: string): string => {
    // Object.hasOwn limita la lectura a propiedades propias (nunca la cadena
    // de prototipos) y Reflect.get evita el acceso computado obj[key] (CTF-006).
    if (!obj || typeof obj !== 'object' || !Object.hasOwn(obj, key)) return '';
    const v: unknown = Reflect.get(obj, key);
    return v === undefined || v === null ? '' : String(v);
  };

  // ── Datos de referencia vía TanStack Query (FE-HIGH-6) ───────────────────────
  // Antes eran useState+useEffect+get con errores tragados; ahora son queries con
  // caché, dedup y manejo de error consistente. Los callbacks (caja/sesión/vendedor
  // predeterminados) se disparan en useEffect sobre la data resuelta.
  const toArray = <T,>(res: unknown): T[] => {
    if (Array.isArray(res)) return res as T[];
    if (res && typeof res === 'object' && 'results' in res && Array.isArray((res as { results: unknown[] }).results)) {
      return (res as { results: T[] }).results;
    }
    return [];
  };

  const cajasQuery = useQuery({
    queryKey: ['venta-ref', 'cajas-usuario'],
    queryFn: () => get('/finanzas/cajas-usuario/'),
    staleTime: 60_000,
  });
  const cajasUsuario = useMemo(() => toArray<CajaUsuario>(cajasQuery.data), [cajasQuery.data]);

  const sesionQuery = useQuery({
    queryKey: ['venta-ref', 'sesion-activa'],
    queryFn: getSesionActiva,
    staleTime: 30_000,
  });
  const sesionActiva = sesionQuery.data ?? null;

  // Empresas solo si no hay sesión activa (o la consulta de sesión falló).
  const empresasQuery = useQuery({
    queryKey: ['venta-ref', 'empresas'],
    queryFn: () => get('/core/empresas/'),
    enabled: (sesionQuery.isSuccess && !sesionQuery.data) || sesionQuery.isError,
    staleTime: 60_000,
  });
  const empresas = useMemo(
    () => toArray<{ id_empresa: string; nombre_legal: string }>(empresasQuery.data),
    [empresasQuery.data],
  );

  const sucursalesQuery = useQuery({
    queryKey: ['venta-ref', 'sucursales', empresaId],
    queryFn: () => get(`/core/sucursales/?id_empresa=${empresaId}`),
    enabled: !!empresaId,
    staleTime: 60_000,
  });
  const sucursales = useMemo(
    () => toArray<{ id_sucursal: string; nombre: string; id_empresa: string }>(sucursalesQuery.data),
    [sucursalesQuery.data],
  );

  const productosQuery = useQuery({
    queryKey: ['venta-ref', 'productos', empresaId],
    queryFn: () => fetchProductos(empresaId),
    enabled: !!empresaId,
    staleTime: 60_000,
  });
  const productos = useMemo(() => toArray<Producto>(productosQuery.data), [productosQuery.data]);

  const vendedoresQuery = useQuery({
    queryKey: ['venta-ref', 'vendedores', empresaId],
    queryFn: () => fetchUsuarios(empresaId || undefined),
    enabled: !!empresaId,
    staleTime: 60_000,
  });
  const vendedores = useMemo(() => toArray<Usuario>(vendedoresQuery.data), [vendedoresQuery.data]);

  // Callbacks de predeterminados, derivados de la data ya resuelta.
  useEffect(() => {
    const cajaPred = cajasUsuario.find(c => c.es_predeterminada);
    if (cajaPred?.caja?.id_caja && onCajaPredet) onCajaPredet(cajaPred.caja.id_caja);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cajasUsuario]);

  useEffect(() => {
    if (sesionActiva && onSesionCargada) onSesionCargada(sesionActiva);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sesionActiva]);

  useEffect(() => {
    if (onVendedorPredet && vendedores.length > 0) {
      const sesionUserId = sesionActiva?.usuario?.id;
      const preferred = sesionUserId && vendedores.some(u => String(u.id) === String(sesionUserId))
        ? String(sesionUserId)
        : String(vendedores[0]?.id ?? '');
      onVendedorPredet(preferred);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vendedores, sesionActiva]);

  // ── Staging de línea de producto (FormularioProducto) ─────────────────────────
  const handleDetalleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setDetalleForm(f => ({ ...f, [e.target.name]: e.target.value }));
  };

  const handleAddDetalle = (e: React.FormEvent) => {
    e.preventDefault();
    if (!detalleForm.id_producto || !detalleForm.cantidad || !detalleForm.precio_unitario) return;
    detallesArray.append({
      id_producto: detalleForm.id_producto,
      cantidad: detalleForm.cantidad,
      precio_unitario: detalleForm.precio_unitario,
      descuento_porcentaje: detalleForm.descuento_porcentaje || '',
      sku: detalleForm.sku || '',
      producto: detalleForm.producto || '',
      comentarios: detalleForm.comentarios || '',
    } as never);
    setDetalleForm(emptyDetalleForm());
    setError('');
  };

  const handleRemoveDetalle = (idx: number) => {
    detallesArray.remove(idx);
  };

  const selectProducto = (prod: Producto) => {
    setDetalleForm(f => ({
      ...f,
      id_producto: prod.id_producto,
      precio_unitario: prod.precio_venta_sugerido !== undefined ? String(prod.precio_venta_sugerido) : '',
      sku: prod.sku || '',
      producto: prod.nombre_producto || '',
    }));
  };

  // ── Cliente ───────────────────────────────────────────────────────────────────
  const selectCliente = (
    cli: Cliente,
    setClienteId: (id: string) => void,
  ) => {
    setClienteId(cli.id_cliente);
    setClienteManual({
      razon_social: cli.razon_social || '',
      rif: cli.rif || '',
      telefono: cli.telefono || '',
      direccion: getFieldString(cli, 'direccion') || getFieldString(cli, 'direccion_fiscal'),
      correo: getFieldString(cli, 'email') || getFieldString(cli, 'correo'),
      codigo_cliente: getFieldString(cli, 'codigo_cliente'),
    });
    setSuccess('Cliente seleccionado correctamente.');
  };

  const handleClienteManualChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target;
    if (name === 'rif_prefijo' || name === 'rif_numero') {
      const [prevPref, prevNum] = clienteManual.rif.split('-');
      const prefijo = name === 'rif_prefijo' ? value : (prevPref || '');
      const numero = name === 'rif_numero' ? value : (prevNum || '');
      setClienteManual(f => ({ ...f, rif: prefijo && numero ? `${prefijo}-${numero}` : prefijo || numero }));
    } else if (isClienteManualKey(name)) {
      setClienteManual(f => ({ ...f, [name]: value }));
    }
  };

  const handleClienteBlur = async () => {
    const eid = empresaId || getEmpresaId() || '';
    if (!eid || !clienteManual.razon_social.trim() || !clienteManual.rif.trim()) return;
    try {
      const similares = await buscarClientesSimilares(clienteManual.razon_social, clienteManual.rif, eid);
      setClientesSimilares(similares);
      if (similares.length > 0) {
        setSuccess(`Se encontraron clientes similares. Considera seleccionar uno existente.`);
      } else {
        setSuccess('');
      }
    } catch {
      // ignore
    }
  };

  const handleClienteManualKeyDown = async (
    e: React.KeyboardEvent<HTMLInputElement>,
    setClienteId: (id: string) => void,
  ) => {
    if (e.key !== 'Enter') return;
    const fieldName = e.currentTarget.name;
    const eid = empresaId || getEmpresaId() || '';
    const query = fieldName === 'razon_social' ? clienteManual.razon_social : clienteManual.rif;
    if (!query) return;

    const results = await buscarClientes(query, eid);
    const normalize = (s: string) => (s || '').trim().toLowerCase();
    const match = results.find(cli =>
      (fieldName === 'razon_social' && normalize(cli.razon_social) === normalize(query)) ||
      (fieldName === 'rif' && normalize(cli.rif) === normalize(query))
    );
    if (match) {
      selectCliente(match, setClienteId);
    }
  };

  const crearClienteAuto = async (
    idEmpresa: string,
  ): Promise<string | null> => {
    if (!clienteManual.razon_social || !clienteManual.rif || !clienteManual.telefono) return null;
    try {
      const nuevoCliente = await crearClienteConEmpresa({
        razon_social: clienteManual.razon_social,
        rif: clienteManual.rif,
        telefono: clienteManual.telefono,
        direccion: clienteManual.direccion,
        correo: clienteManual.correo,
        id_empresa: idEmpresa,
      });
      setSuccess('Cliente creado y seleccionado correctamente.');
      return nuevoCliente.id_cliente;
    } catch {
      setError('Error al crear el cliente');
      return null;
    }
  };

  /** Resetea estado auxiliar tras una creación exitosa. */
  const resetAuxState = () => {
    setDetalleForm(emptyDetalleForm());
    setPagos([]);
    setDescuentoGeneral('');
    setClienteManual({ razon_social: '', rif: '', telefono: '', direccion: '', correo: '', codigo_cliente: '' });
  };

  /** Helper para fijar el id_cliente en el formulario RHF. */
  const setClienteId = (id: string) => setValue('id_cliente' as Path<TForm>, id as never, { shouldDirty: true });

  return {
    // react-hook-form primitives
    control,
    register,
    handleSubmit,
    reset,
    setValue,
    watch,
    getValues,
    formState,
    detallesArray,
    setClienteId,
    emptyDetalleForm,
    empresaId,
    // Estado auxiliar
    error, setError,
    success, setSuccess,
    loading, setLoading,
    productos,
    detalleForm, setDetalleForm,
    descuentoGeneral, setDescuentoGeneral,
    pagos, setPagos,
    clienteManual, setClienteManual,
    cajasUsuario,
    sesionActiva,
    vendedores,
    clientesSimilares,
    empresas,
    sucursales,
    // Utilities
    getFieldString,
    crearClienteAuto,
    resetAuxState,
    // Handlers
    handleDetalleChange,
    handleAddDetalle,
    handleRemoveDetalle,
    selectProducto,
    selectCliente,
    handleClienteManualChange,
    handleClienteBlur,
    handleClienteManualKeyDown,
  };
};
