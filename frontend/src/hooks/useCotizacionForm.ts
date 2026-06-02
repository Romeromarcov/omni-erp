import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { Cotizacion, DetalleCotizacion } from '../types/ventas';
import { get } from '../services/api';
import { pagosService } from '../services/pagosService';
import { getEmpresaId } from '../utils/empresa';
import type { Pago } from '../components/Pedidos/ModalPago';
import { cotizacionService } from '../services/ventas';
import { useDocumentoVentaBase } from './useDocumentoVentaBase';
import { subtotalLinea } from '../lib/decimal';
import { cotizacionFormSchema, type CotizacionFormInput } from '../schemas/ventas.schemas';

const initialForm = (): CotizacionFormInput => ({
  numero_cotizacion: '',
  fecha_cotizacion: new Date().toISOString().slice(0, 10),
  fecha_vencimiento: new Date(Date.now() + 30 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10),
  estado: 'BORRADOR',
  id_empresa: getEmpresaId() || '',
  id_sucursal: localStorage.getItem('id_sucursal') || '',
  id_cliente: '',
  id_moneda: '',
  id_caja: '',
  id_vendedor: '',
  observaciones: '',
  condiciones_comerciales: '',
  detalles: [],
});

export const useCotizacionForm = (cotizacionId?: string) => {
  const [numeroCotizacionCreado, setNumeroCotizacionCreado] = useState<string | null>(null);

  const base = useDocumentoVentaBase<CotizacionFormInput>({
    schema: cotizacionFormSchema,
    defaultValues: initialForm(),
    onCajaPredet: (cajaId) => { if (!base.watch('id_caja')) base.setValue('id_caja', cajaId); },
    onSesionCargada: (sesion) => {
      if (sesion?.caja_fisica_principal) {
        base.setValue('id_caja', sesion.caja_fisica_principal.id_caja);
        base.setValue('id_sucursal', sesion.caja_fisica_principal.sucursal.id_sucursal);
        base.setValue('id_empresa', sesion.caja_fisica_principal.sucursal.empresa.id_empresa);
      }
    },
    onVendedorPredet: (userId) => { if (!base.watch('id_vendedor')) base.setValue('id_vendedor', userId); },
  });

  const { data: cotizacionData, isLoading: isLoadingCotizacion } = useQuery({
    queryKey: ['cotizaciones', cotizacionId],
    queryFn: () => get(`/ventas/cotizaciones/${cotizacionId}/`) as Promise<Cotizacion>,
    enabled: !!cotizacionId,
  });

  useEffect(() => {
    if (isLoadingCotizacion) { base.setLoading(true); return; }
    if (!cotizacionData) { base.setLoading(false); return; }
    // FE-HIGH-6: no pisar ediciones en curso.
    if (base.formState.isDirty) { base.setLoading(false); return; }
    const cotizacion = cotizacionData;
    base.reset({
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
      detalles: Array.isArray(cotizacion.detalles)
        ? cotizacion.detalles.map((d: DetalleCotizacion) => ({
            id_producto: d.id_producto || '',
            cantidad: String(d.cantidad ?? 0),
            precio_unitario: String(d.precio_unitario ?? 0),
            descuento_porcentaje: String(d.descuento_porcentaje ?? ''),
            sku: d.sku || '',
            producto: d.producto || '',
            comentarios: '',
          }))
        : [],
    });
    base.setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cotizacionData, isLoadingCotizacion]);

  // FE-HIGH-5: el número de cotización lo asigna el backend al guardar.

  const submitCotizacion = async (values: CotizacionFormInput, pagosToSend?: Pago[]) => {
    base.setLoading(true);
    base.setError('');
    base.setSuccess('');

    let idClienteFinal = values.id_cliente || '';
    if (!idClienteFinal) {
      const newId = await base.crearClienteAuto(values.id_empresa);
      if (!newId) { base.setLoading(false); return null; }
      idClienteFinal = newId;
      base.setValue('id_cliente', newId);
    }

    const detallesConSubtotal = values.detalles.map(d => ({
      ...d,
      subtotal: subtotalLinea(d.cantidad, d.precio_unitario, d.descuento_porcentaje).toFixed(2),
    }));
    const payload: Record<string, unknown> = { ...values, id_cliente: idClienteFinal, detalles: detallesConSubtotal };
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

        base.reset(initialForm());
        base.resetAuxState();
      }
      base.setLoading(false);
      return response?.numero_cotizacion || '';
    } catch {
      base.setError('Error al crear la cotización');
      base.setLoading(false);
      return null;
    }
  };

  const handleClienteManualKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) =>
    void base.handleClienteManualKeyDown(e, base.setClienteId);

  return {
    ...base,
    numeroCotizacionCreado,
    submitCotizacion,
    handleClienteManualKeyDown,
  };
};
