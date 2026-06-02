import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { FacturaFiscal, DetalleFacturaFiscal } from '../types/ventas';
import { get } from '../services/api';
import { pagosService } from '../services/pagosService';
import { getEmpresaId } from '../utils/empresa';
import type { Pago } from '../components/Pedidos/ModalPago';
import { FacturaFiscalService } from '../services/ventas';
import { useDocumentoVentaBase } from './useDocumentoVentaBase';
import { D } from '../lib/decimal';
import { facturaFiscalFormSchema, type FacturaFiscalFormInput } from '../schemas/ventas.schemas';

const facturaFiscalService = new FacturaFiscalService();

const initialForm = (): FacturaFiscalFormInput => ({
  numero_factura: '',
  fecha_emision: new Date().toISOString().slice(0, 10),
  id_empresa: getEmpresaId() || '',
  id_sucursal: localStorage.getItem('id_sucursal') || '',
  id_cliente: '',
  id_caja: '',
  id_vendedor: '',
  observaciones: '',
  detalles: [],
});

export const useFacturaFiscalForm = (facturaId?: string) => {
  const [numeroFacturaCreado, setNumeroFacturaCreado] = useState<string | null>(null);

  const base = useDocumentoVentaBase<FacturaFiscalFormInput>({
    schema: facturaFiscalFormSchema,
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

  const { data: facturaData, isLoading: isLoadingFactura } = useQuery({
    queryKey: ['facturas-fiscales', facturaId],
    queryFn: () => get(`/ventas/facturas-fiscales/${facturaId}/`) as Promise<FacturaFiscal>,
    enabled: !!facturaId,
  });

  useEffect(() => {
    if (isLoadingFactura) { base.setLoading(true); return; }
    if (!facturaData) { base.setLoading(false); return; }
    if (base.formState.isDirty) { base.setLoading(false); return; }
    const factura = facturaData;
    base.reset({
      numero_factura: factura.numero_factura || '',
      fecha_emision: (factura.fecha_emision || '').slice(0, 10) || new Date().toISOString().slice(0, 10),
      id_empresa: factura.id_empresa || getEmpresaId() || '',
      id_sucursal: localStorage.getItem('id_sucursal') || '',
      id_cliente: factura.id_cliente?.id_cliente || '',
      id_caja: factura.id_caja || '',
      id_vendedor: factura.id_vendedor || '',
      observaciones: factura.observaciones || '',
      detalles: Array.isArray(factura.detalles)
        ? (factura.detalles as DetalleFacturaFiscal[]).map(d => ({
            id_producto: d.id_producto || '',
            cantidad: String(d.cantidad ?? 0),
            precio_unitario: String(d.precio_unitario ?? 0),
            descuento_porcentaje: String(d.descuento_porcentaje ?? ''),
            sku: '',
            producto: '',
            comentarios: '',
          }))
        : [],
    });
    base.setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facturaData, isLoadingFactura]);

  const submitFacturaFiscal = async (values: FacturaFiscalFormInput, pagosToSend?: Pago[]) => {
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
      id_producto: d.id_producto,
      cantidad: Number(d.cantidad),
      precio_unitario: Number(d.precio_unitario),
      descuento_porcentaje: Number(d.descuento_porcentaje || 0),
      subtotal: D(d.cantidad).times(D(d.precio_unitario)).toFixed(2),
    }));
    const payload: Record<string, unknown> = {
      ...values,
      id_cliente: { id_cliente: idClienteFinal },
      detalles: detallesConSubtotal,
    };
    delete payload.numero_factura;

    try {
      let response: { id_factura?: string; numero_factura?: string };
      if (facturaId) {
        response = await facturaFiscalService.update(facturaId, payload as Parameters<typeof facturaFiscalService.update>[1]);
        base.setSuccess('Factura fiscal actualizada exitosamente.');
      } else {
        response = await facturaFiscalService.create(payload as Parameters<typeof facturaFiscalService.create>[0]);
        const numFactura = response?.numero_factura || '';
        const idCreado = response?.id_factura || '';
        setNumeroFacturaCreado(numFactura);
        base.setSuccess(`Factura fiscal creada exitosamente${numFactura ? ` (N° ${numFactura})` : ''}.`);

        const pagosAEnviar = pagosToSend ?? base.pagos;
        if (pagosAEnviar.length > 0 && idCreado) {
          try {
            for (const pago of pagosAEnviar) {
              await pagosService.createPagoDocumento('FACTURA_FISCAL', idCreado, pago);
            }
          } catch {
            base.setSuccess(`Factura fiscal creada${numFactura ? ` (N° ${numFactura})` : ''}, pero hubo un error con los pagos.`);
          }
        }

        base.reset(initialForm());
        base.resetAuxState();
      }
      base.setLoading(false);
      return response?.numero_factura || '';
    } catch {
      base.setError('Error al crear la factura fiscal');
      base.setLoading(false);
      return null;
    }
  };

  const handleClienteManualKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) =>
    void base.handleClienteManualKeyDown(e, base.setClienteId);

  return {
    ...base,
    numeroFacturaCreado,
    submitFacturaFiscal,
    handleClienteManualKeyDown,
  };
};
