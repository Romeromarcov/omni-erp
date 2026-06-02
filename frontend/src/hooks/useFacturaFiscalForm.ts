import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { DetalleFacturaFiscal } from '../types/ventas';
import { get } from '../services/api';
import { pagosService } from '../services/pagosService';
import { getEmpresaId } from '../utils/empresa';
import type { Pago } from '../components/Pedidos/ModalPago';
import { FacturaFiscalService } from '../services/ventas';
import { useDocumentoVentaBase } from './useDocumentoVentaBase';
import { D } from '../lib/decimal';

interface FacturaFiscalForm {
  numero_factura: string;
  fecha_emision: string;
  id_empresa: string;
  id_sucursal: string;
  id_cliente: string;
  id_caja?: string;
  id_vendedor?: string;
  observaciones?: string;
}

const facturaFiscalService = new FacturaFiscalService();

const initialForm = (): FacturaFiscalForm => ({
  numero_factura: '',
  fecha_emision: new Date().toISOString().slice(0, 10),
  id_empresa: getEmpresaId() || '',
  id_sucursal: localStorage.getItem('id_sucursal') || '',
  id_cliente: '',
  id_vendedor: '',
  observaciones: '',
});

export const useFacturaFiscalForm = (facturaId?: string) => {
  const [form, setForm] = useState<FacturaFiscalForm>(initialForm());
  const [numeroFacturaCreado, setNumeroFacturaCreado] = useState<string | null>(null);

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
    setForm(f => ({ ...f, [name as keyof FacturaFiscalForm]: value }));
    base.setError('');
    base.setSuccess('');
  };

  // Load existing factura fiscal
  const { data: facturaData, isLoading: isLoadingFactura } = useQuery({
    queryKey: ['facturas-fiscales', facturaId],
    queryFn: () => get(`/ventas/facturas-fiscales/${facturaId}/`) as Promise<Record<string, unknown>>,
    enabled: !!facturaId,
  });

  useEffect(() => {
    if (isLoadingFactura) {
      base.setLoading(true);
      return;
    }
    if (!facturaData) {
      if (!isLoadingFactura) base.setLoading(false);
      return;
    }
    const factura = facturaData;
    setForm({
      numero_factura: String(factura.numero_factura || ''),
      fecha_emision: String(factura.fecha_emision || '').slice(0, 10) || new Date().toISOString().slice(0, 10),
      id_empresa: String(factura.id_empresa || getEmpresaId() || ''),
      id_sucursal: localStorage.getItem('id_sucursal') || '',
      id_cliente: String((factura.id_cliente as Record<string, unknown>)?.id_cliente || ''),
      id_caja: String(factura.id_caja || ''),
      id_vendedor: String(factura.id_vendedor || ''),
      observaciones: String(factura.observaciones || ''),
    });
    if (Array.isArray(factura.detalles)) {
      base.setDetalles(
        (factura.detalles as DetalleFacturaFiscal[]).map(d => ({
          id_producto: String((d as unknown as Record<string, unknown>).id_producto || ''),
          cantidad: String(d.cantidad ?? 0),
          precio_unitario: String(d.precio_unitario ?? 0),
          descuento_porcentaje: String((d as unknown as { descuento_porcentaje?: number }).descuento_porcentaje ?? ''),
          sku: '',
          producto: '',
        }))
      );
    }
    base.setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [facturaData, isLoadingFactura]);

  const submitFacturaFiscal = async (pagosToSend?: Pago[]) => {
    base.setLoading(true);
    base.setError('');
    base.setSuccess('');

    if (!form.fecha_emision || !form.id_empresa || !form.id_sucursal) {
      base.setError('Todos los campos obligatorios deben estar completos.');
      base.setLoading(false);
      return null;
    }
    if (base.detalles.length === 0) {
      base.setError('Debe agregar al menos un producto a la factura fiscal.');
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
      base.setError('Debe seleccionar un cliente antes de guardar la factura fiscal.');
      base.setLoading(false);
      return null;
    }

    const detallesConSubtotal = base.detalles.map(d => ({
      id_producto: d.id_producto,
      cantidad: Number(d.cantidad),
      precio_unitario: Number(d.precio_unitario),
      descuento_porcentaje: Number(d.descuento_porcentaje || 0),
      subtotal: D(d.cantidad).times(D(d.precio_unitario)).toFixed(2),
    }));
    const payload: Record<string, unknown> = {
      ...form,
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

        setForm(initialForm());
        base.setDetalles([]);
        base.setDetalleForm({ id_producto: '', cantidad: '', precio_unitario: '', descuento_porcentaje: '', sku: '', producto: '' });
        base.setPagos([]);
        base.setClienteManual({ razon_social: '', rif: '', telefono: '', direccion: '', correo: '', codigo_cliente: '' });
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
    void base.handleClienteManualKeyDown(e, (id) => setForm(f => ({ ...f, id_cliente: id })));

  return {
    form,
    setForm,
    handleChange,
    numeroFacturaCreado,
    submitFacturaFiscal,
    ...base,
    handleClienteManualKeyDown,
  };
};
