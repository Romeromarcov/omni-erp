/**
 * Base hook for all sales document forms (Cotizacion, Pedido, NotaVenta, FacturaFiscal).
 * Extracts shared state, effects, and handlers to avoid ~400 lines of duplication per hook.
 */
import { useState, useEffect } from 'react';
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

export interface DetalleDocumentoForm {
  id_producto: string;
  cantidad: string;
  precio_unitario: string;
  descuento_porcentaje?: string;
  sku?: string;
  producto?: string;
}

interface UseDocumentoVentaBaseOptions {
  empresaId: string;
  onCajaPredet?: (cajaId: string) => void;
  onSesionCargada?: (sesion: SesionCaja) => void;
  onVendedorPredet?: (userId: string) => void;
}

export const useDocumentoVentaBase = ({
  empresaId,
  onCajaPredet,
  onSesionCargada,
  onVendedorPredet,
}: UseDocumentoVentaBaseOptions) => {
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [loading, setLoading] = useState(false);
  const [productos, setProductos] = useState<Producto[]>([]);
  const [detalles, setDetalles] = useState<DetalleDocumentoForm[]>([]);
  const [detalleForm, setDetalleForm] = useState<DetalleDocumentoForm>({
    id_producto: '', cantidad: '', precio_unitario: '', descuento_porcentaje: '', sku: '', producto: '',
  });
  const [descuentoGeneral, setDescuentoGeneral] = useState('');
  const [pagos, setPagos] = useState<Pago[]>([]);
  const [clienteManual, setClienteManual] = useState<ClienteManual>({
    razon_social: '', rif: '', telefono: '', direccion: '', correo: '', codigo_cliente: '',
  });
  const [cajasUsuario, setCajasUsuario] = useState<CajaUsuario[]>([]);
  const [sesionActiva, setSesionActiva] = useState<SesionCaja | null>(null);
  const [vendedores, setVendedores] = useState<Usuario[]>([]);
  const [clientesSimilares, setClientesSimilares] = useState<Cliente[]>([]);
  const [empresas, setEmpresas] = useState<Array<{ id_empresa: string; nombre_legal: string }>>([]);
  const [sucursales, setSucursales] = useState<Array<{ id_sucursal: string; nombre: string; id_empresa: string }>>([]);

  const getFieldString = (obj: unknown, key: string): string => {
    if (!obj || typeof obj !== 'object') return '';
    const v = (obj as Record<string, unknown>)[key];
    return v === undefined || v === null ? '' : String(v);
  };

  const loadEmpresas = async () => {
    try {
      const res = await get('/core/empresas/');
      if (Array.isArray(res)) setEmpresas(res);
      else if (res && typeof res === 'object' && 'results' in res && Array.isArray((res as { results: unknown[] }).results)) {
        setEmpresas((res as { results: Array<{ id_empresa: string; nombre_legal: string }> }).results);
      }
    } catch {
      // silent — user may not have access to all companies
    }
  };

  useEffect(() => {
    const fetchCajasUsuario = async () => {
      try {
        const res = await get('/finanzas/cajas-usuario/');
        if (Array.isArray(res)) {
          setCajasUsuario(res);
          const cajaPred = (res as CajaUsuario[]).find(c => c.es_predeterminada);
          if (cajaPred?.caja?.id_caja && onCajaPredet) {
            onCajaPredet(cajaPred.caja.id_caja);
          }
        }
      } catch {
        // ignore
      }
    };
    fetchCajasUsuario();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const fetchSesion = async () => {
      try {
        const sesion = await getSesionActiva();
        setSesionActiva(sesion);
        if (sesion) {
          onSesionCargada?.(sesion);
        } else {
          await loadEmpresas();
        }
      } catch {
        await loadEmpresas();
      }
    };
    fetchSesion();
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!empresaId) { setSucursales([]); return; }
    get(`/core/sucursales/?id_empresa=${empresaId}`)
      .then(res => {
        if (Array.isArray(res)) setSucursales(res);
        else if (res && typeof res === 'object' && 'results' in res) {
          setSucursales((res as { results: Array<{ id_sucursal: string; nombre: string; id_empresa: string }> }).results);
        }
      })
      .catch(() => setSucursales([]));
  }, [empresaId]);

  useEffect(() => {
    if (!empresaId) { setProductos([]); return; }
    fetchProductos(empresaId)
      .then(res => {
        if (Array.isArray(res)) setProductos(res);
        else if (res && typeof res === 'object' && 'results' in res) {
          setProductos((res as { results: Producto[] }).results);
        } else setProductos([]);
      })
      .catch(() => setProductos([]));
  }, [empresaId]);

  useEffect(() => {
    if (!empresaId) return;
    fetchUsuarios(empresaId || undefined)
      .then(users => {
        const arr = Array.isArray(users) ? users : [];
        setVendedores(arr);
        if (onVendedorPredet && arr.length > 0) {
          const sesionUserId = sesionActiva?.usuario?.id;
          const preferred = sesionUserId && arr.some(u => String(u.id) === String(sesionUserId))
            ? String(sesionUserId)
            : String(arr[0].id);
          onVendedorPredet(preferred);
        }
      })
      .catch(() => {});
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [empresaId, sesionActiva]);

  const handleDetalleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    setDetalleForm(f => ({ ...f, [e.target.name]: e.target.value }));
  };

  const handleAddDetalle = (e: React.FormEvent) => {
    e.preventDefault();
    if (!detalleForm.id_producto || !detalleForm.cantidad || !detalleForm.precio_unitario) return;
    setDetalles(dets => [...dets, { ...detalleForm }]);
    setDetalleForm({ id_producto: '', cantidad: '', precio_unitario: '', descuento_porcentaje: '', sku: '', producto: '' });
    setError('');
  };

  const handleRemoveDetalle = (idx: number) => {
    setDetalles(dets => dets.filter((_, i) => i !== idx));
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
    } else {
      setClienteManual(f => ({ ...f, [name as keyof ClienteManual]: value }));
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

  return {
    // State
    error, setError,
    success, setSuccess,
    loading, setLoading,
    productos,
    detalles, setDetalles,
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
