import { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { NotaVenta, DetalleNotaVenta } from '../types/ventas';
import { get } from '../services/api';
import { pagosService } from '../services/pagosService';
import { getEmpresaId } from '../utils/empresa';
import type { Pago } from '../components/Pedidos/ModalPago';
import { NotaVentaService } from '../services/ventas';
import { useDocumentoVentaBase } from './useDocumentoVentaBase';

interface NotaVentaForm {
  numero_nota_venta: string;
  fecha_emision: string;
  id_empresa: string;
  id_sucursal: string;
  id_cliente: string;
  id_caja?: string;
  id_vendedor?: string;
  observaciones?: string;
}

const notaVentaService = new NotaVentaService();

const initialForm = (): NotaVentaForm => ({
  numero_nota_venta: '',
  fecha_emision: new Date().toISOString().slice(0, 10),
  id_empresa: getEmpresaId() || '',
  id_sucursal: localStorage.getItem('id_sucursal') || '',
  id_cliente: '',
  id_vendedor: '',
  observaciones: '',
});

export const useNotaVentaForm = (notaVentaId?: string) => {
  const [form, setForm] = useState<NotaVentaForm>(initialForm());
  const [numeroNotaVentaCreado, setNumeroNotaVentaCreado] = useState<string | null>(null);

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
    setForm(f => ({ ...f, [name as keyof NotaVentaForm]: value }));
    base.setError('');
    base.setSuccess('');
  };

  // Load existing nota de venta
  const { data: notaData, isLoading: isLoadingNota } = useQuery({
    queryKey: ['notas-venta', notaVentaId],
    queryFn: () => get(`/ventas/notas-venta/${notaVentaId}/`) as Promise<NotaVenta>,
    enabled: !!notaVentaId,
  });

  useEffect(() => {
    if (isLoadingNota) {
      base.setLoading(true);
      return;
    }
    if (!notaData) {
      if (!isLoadingNota) base.setLoading(false);
      return;
    }
    const n = notaData as unknown as Record<string, unknown>;
    const nota = notaData;
    setForm({
      numero_nota_venta: String(n.numero_nota_venta || ''),
      fecha_emision: String(n.fecha_emision || '').slice(0, 10) || new Date().toISOString().slice(0, 10),
      id_empresa: String(n.id_empresa || getEmpresaId() || ''),
      id_sucursal: localStorage.getItem('id_sucursal') || '',
      id_cliente: String((n.id_cliente as Record<string, unknown>)?.id_cliente || ''),
      id_caja: String(n.id_caja || ''),
      id_vendedor: String(n.id_vendedor || ''),
      observaciones: String(n.observaciones || ''),
    });
    if (Array.isArray(nota.detalles)) {
      base.setDetalles(
        nota.detalles.map((d: DetalleNotaVenta) => ({
          id_producto: String((d as unknown as Record<string, unknown>).id_producto || ''),
          cantidad: String(d.cantidad ?? 0),
          precio_unitario: String(d.precio_unitario ?? 0),
          descuento_porcentaje: '',
          sku: '',
          producto: '',
        }))
      );
    }
    base.setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notaData, isLoadingNota]);

  const submitNotaVenta = async (pagosToSend?: Pago[]) => {
    base.setLoading(true);
    base.setError('');
    base.setSuccess('');

    if (!form.fecha_emision || !form.id_empresa || !form.id_sucursal) {
      base.setError('Todos los campos obligatorios deben estar completos.');
      base.setLoading(false);
      return null;
    }
    if (base.detalles.length === 0) {
      base.setError('Debe agregar al menos un producto a la nota de venta.');
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
      base.setError('Debe seleccionar un cliente antes de guardar la nota de venta.');
      base.setLoading(false);
      return null;
    }

    const detallesConSubtotal = base.detalles.map(d => ({
      id_producto: d.id_producto,
      cantidad: Number(d.cantidad),
      precio_unitario: Number(d.precio_unitario),
      subtotal: Number(d.cantidad) * Number(d.precio_unitario),
    }));
    const payload: Record<string, unknown> = {
      ...form,
      id_cliente: { id_cliente: idClienteFinal },
      detalles: detallesConSubtotal,
    };
    delete payload.numero_nota_venta;

    try {
      let response: { id_nota_venta?: string; numero_nota_venta?: string };
      if (notaVentaId) {
        response = await notaVentaService.update(notaVentaId, payload as Parameters<typeof notaVentaService.update>[1]);
        base.setSuccess('Nota de venta actualizada exitosamente.');
      } else {
        response = await notaVentaService.create(payload as Parameters<typeof notaVentaService.create>[0]);
        const numNota = response?.numero_nota_venta || '';
        const idCreado = response?.id_nota_venta || '';
        setNumeroNotaVentaCreado(numNota);
        base.setSuccess(`Nota de venta creada exitosamente${numNota ? ` (N° ${numNota})` : ''}.`);

        const pagosAEnviar = pagosToSend ?? base.pagos;
        if (pagosAEnviar.length > 0 && idCreado) {
          try {
            for (const pago of pagosAEnviar) {
              await pagosService.createPagoDocumento('NOTA_VENTA', idCreado, pago);
            }
          } catch {
            base.setSuccess(`Nota de venta creada${numNota ? ` (N° ${numNota})` : ''}, pero hubo un error con los pagos.`);
          }
        }

        setForm(initialForm());
        base.setDetalles([]);
        base.setDetalleForm({ id_producto: '', cantidad: '', precio_unitario: '', descuento_porcentaje: '', sku: '', producto: '' });
        base.setPagos([]);
        base.setClienteManual({ razon_social: '', rif: '', telefono: '', direccion: '', correo: '', codigo_cliente: '' });
      }
      base.setLoading(false);
      return response?.numero_nota_venta || '';
    } catch {
      base.setError('Error al crear la nota de venta');
      base.setLoading(false);
      return null;
    }
  };

  return {
    form,
    setForm,
    handleChange,
    numeroNotaVentaCreado,
    submitNotaVenta,
    ...base,
  };
};
