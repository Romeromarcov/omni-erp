import { useState, useEffect } from 'react';
import type { Cotizacion, DetalleCotizacion } from '../types/ventas';
import { get } from '../services/api';
import { pagosService } from '../services/pagosService';
import { getEmpresaId } from '../utils/empresa';
import type { Pago } from '../components/Pedidos/ModalPago';
import { cotizacionService } from '../services/ventas';
import {
  useDocumentoVentaBase,
} from './useDocumentoVentaBase';

interface CotizacionForm {
  numero_cotizacion: string;
  fecha_cotizacion: string;
  fecha_vencimiento: string;
  estado: string;
  id_empresa: string;
  id_sucursal: string;
  id_cliente: string;
  id_moneda: string;
  id_caja?: string;
  id_vendedor?: string;
  observaciones?: string;
  condiciones_comerciales?: string;
}

const initialForm = (): CotizacionForm => ({
  numero_cotizacion: '',
  fecha_cotizacion: new Date().toISOString().slice(0, 10),
  fecha_vencimiento: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
  estado: 'BORRADOR',
  id_empresa: getEmpresaId() || '',
  id_sucursal: localStorage.getItem('id_sucursal') || '',
  id_cliente: '',
  id_moneda: '',
  id_vendedor: '',
  observaciones: '',
  condiciones_comerciales: '',
});

export const useCotizacionForm = (cotizacionId?: string) => {
  const [form, setForm] = useState<CotizacionForm>(initialForm());
  const [numeroCotizacionCreado, setNumeroCotizacionCreado] = useState<string | null>(null);

  const base = useDocumentoVentaBase({
    empresaId: form.id_empresa,
    onCajaPredet: (cajaId) => setForm(f => f.id_caja ? f : { ...f, id_caja: cajaId }),
    onSesionCargada: (sesion) => {
      if (sesion?.caja_fisica_principal) {
        setForm(f => ({
          ...f,
          id_caja: sesion.caja_fisica_principal.id_caja,
          id_sucursal: sesion.caja_fisica_principal.sucursal.id_sucursal,
          id_empresa: sesion.caja_fisica_principal.sucursal.empresa.id_empresa,
        }));
      }
    },
    onVendedorPredet: (userId) => setForm(f => f.id_vendedor ? f : { ...f, id_vendedor: userId }),
  });

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) => {
    const { name, value } = e.target;
    setForm(f => ({ ...f, [name as keyof CotizacionForm]: value }));
    base.setError('');
    base.setSuccess('');
  };

  // Load existing cotizacion
  useEffect(() => {
    if (!cotizacionId) return;
    base.setLoading(true);
    get(`/ventas/cotizaciones/${cotizacionId}/`)
      .then((cotizacion: Cotizacion) => {
        setForm({
          numero_cotizacion: cotizacion.numero_cotizacion || '',
          fecha_cotizacion: cotizacion.fecha_cotizacion?.slice(0, 10) ?? new Date().toISOString().slice(0, 10),
          fecha_vencimiento: cotizacion.fecha_vencimiento?.slice(0, 10) ?? '',
          estado: cotizacion.estado || 'BORRADOR',
          id_empresa: cotizacion.id_empresa || getEmpresaId() || '',
          id_sucursal: localStorage.getItem('id_sucursal') || '',
          id_cliente: cotizacion.id_cliente?.id_cliente || '',
          id_moneda: cotizacion.id_moneda || '',
          id_caja: cotizacion.id_caja || '',
          id_vendedor: cotizacion.id_vendedor || '',
          observaciones: cotizacion.observaciones || '',
          condiciones_comerciales: cotizacion.condiciones_comerciales || '',
        });
        if (cotizacion.detalles && Array.isArray(cotizacion.detalles)) {
          base.setDetalles(
            cotizacion.detalles.map((d: DetalleCotizacion) => ({
              id_producto: d.id_producto || '',
              cantidad: String(d.cantidad ?? 0),
              precio_unitario: String(d.precio_unitario ?? 0),
              descuento_porcentaje: String(d.descuento_porcentaje ?? ''),
              sku: (d as unknown as { sku?: string }).sku || '',
              producto: (d as unknown as { producto?: string }).producto || '',
            }))
          );
        }
      })
      .catch(() => base.setError('Error al cargar la cotización'))
      .finally(() => base.setLoading(false));
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cotizacionId]);

  // Fetch next cotizacion number
  useEffect(() => {
    get('/ventas/cotizaciones/?ordering=-numero_cotizacion&limit=1')
      .then(res => {
        let ultimo = '';
        const results = (res as { results?: { numero_cotizacion: string }[] })?.results;
        if (Array.isArray(results) && results.length > 0) {
          ultimo = results[0].numero_cotizacion;
        } else if (Array.isArray(res) && (res as { numero_cotizacion: string }[]).length > 0) {
          ultimo = (res as { numero_cotizacion: string }[])[0].numero_cotizacion;
        }
        const num = ultimo
          ? (parseInt(ultimo.replace(/\D/g, ''), 10) + 1).toString().padStart(6, '0')
          : '000001';
        setNumeroCotizacionCreado(num);
      })
      .catch(() => setNumeroCotizacionCreado('000001'));
  }, []);

  const submitCotizacion = async (pagosToSend?: Pago[]) => {
    base.setLoading(true);
    base.setError('');
    base.setSuccess('');

    if (!form.fecha_cotizacion || !form.id_empresa || !form.id_sucursal || !form.id_moneda) {
      base.setError('Todos los campos obligatorios deben estar completos.');
      base.setLoading(false);
      return null;
    }
    if (base.detalles.length === 0) {
      base.setError('Debe agregar al menos un producto a la cotización.');
      base.setLoading(false);
      return null;
    }

    let idClienteFinal = form.id_cliente;
    if (!idClienteFinal) {
      const newId = await base.crearClienteAuto(form.id_empresa);
      if (!newId) { base.setLoading(false); return null; }
      idClienteFinal = newId;
      setForm(f => ({ ...f, id_cliente: newId }));
    }
    if (!idClienteFinal) {
      base.setError('Debe seleccionar un cliente antes de guardar la cotización.');
      base.setLoading(false);
      return null;
    }

    const detallesConSubtotal = base.detalles.map(d => ({
      ...d,
      subtotal: String(Number(d.cantidad) * Number(d.precio_unitario) * (1 - Number(d.descuento_porcentaje || 0) / 100)),
    }));
    const payload: Record<string, unknown> = { ...form, id_cliente: idClienteFinal, detalles: detallesConSubtotal };
    if (!cotizacionId) delete payload.numero_cotizacion;

    try {
      let response: { id_cotizacion?: string; numero_cotizacion?: string };
      if (cotizacionId) {
        response = await cotizacionService.update(cotizacionId, payload as Parameters<typeof cotizacionService.update>[1]);
        base.setSuccess('Cotización actualizada exitosamente.');
      } else {
        response = await cotizacionService.create(payload as Parameters<typeof cotizacionService.create>[0]);
        const numCot = response?.numero_cotizacion || '';
        const idCreado = response?.id_cotizacion || '';
        setNumeroCotizacionCreado(numCot);
        base.setSuccess(`Cotización creada exitosamente${numCot ? ` (N° ${numCot})` : ''}.`);

        const pagosAEnviar = pagosToSend ?? base.pagos;
        if (pagosAEnviar.length > 0 && idCreado) {
          try {
            for (const pago of pagosAEnviar) {
              await pagosService.createPagoDocumento('COTIZACION', idCreado, pago);
            }
          } catch {
            base.setSuccess(`Cotización creada${numCot ? ` (N° ${numCot})` : ''}, pero hubo un error con los pagos.`);
          }
        }

        setForm(initialForm());
        base.setDetalles([]);
        base.setDetalleForm({ id_producto: '', cantidad: '', precio_unitario: '', descuento_porcentaje: '', sku: '', producto: '' });
        base.setPagos([]);
        base.setClienteManual({ razon_social: '', rif: '', telefono: '', direccion: '', correo: '', codigo_cliente: '' });
      }
      base.setLoading(false);
      return response?.numero_cotizacion || '';
    } catch {
      base.setError('Error al crear la cotización');
      base.setLoading(false);
      return null;
    }
  };

  return {
    form,
    setForm,
    handleChange,
    numeroCotizacionCreado,
    submitCotizacion,
    ...base,
  };
};
