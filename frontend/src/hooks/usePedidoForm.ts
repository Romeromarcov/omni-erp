import React, { useState, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { Pedido, DetallePedido } from '../types/ventas';
import { post, get, patch } from '../services/api';
import { pagosService } from '../services/pagosService';
import { getEmpresaId } from '../utils/empresa';
import type { Pago } from '../components/Pedidos/ModalPago';
import { useDocumentoVentaBase } from './useDocumentoVentaBase';

interface PedidoForm {
  numero_pedido: string;
  fecha_pedido: string;
  id_empresa: string;
  id_sucursal: string;
  id_cliente: string;
  id_caja?: string;
  id_vendedor?: string;
  observaciones?: string;
}

const initialForm = (): PedidoForm => ({
  numero_pedido: '',
  fecha_pedido: new Date().toISOString().slice(0, 10),
  id_empresa: getEmpresaId() || '',
  id_sucursal: localStorage.getItem('id_sucursal') || '',
  id_cliente: '',
  id_vendedor: '',
  observaciones: '',
});

export const usePedidoForm = (pedidoId?: string) => {
  const [form, setForm] = useState<PedidoForm>(initialForm());
  const [numeroPedidoCreado, setNumeroPedidoCreado] = useState<string | null>(null);

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
    setForm(f => ({ ...f, [name as keyof PedidoForm]: value }));
    base.setError('');
    base.setSuccess('');
  };

  // Load existing pedido
  const { data: pedidoData, isLoading: isLoadingPedido } = useQuery({
    queryKey: ['pedidos', pedidoId],
    queryFn: () => get(`/ventas/pedidos/${pedidoId}/`) as Promise<Pedido>,
    enabled: !!pedidoId,
  });

  useEffect(() => {
    if (isLoadingPedido) {
      base.setLoading(true);
      return;
    }
    if (!pedidoData) {
      if (!isLoadingPedido) base.setLoading(false);
      return;
    }
    const pedido = pedidoData;
    setForm({
      numero_pedido: pedido.numero_pedido || '',
      fecha_pedido: pedido.fecha_pedido?.slice(0, 10) ?? new Date().toISOString().slice(0, 10),
      id_empresa: (pedido as unknown as { id_empresa: string }).id_empresa || getEmpresaId() || '',
      id_sucursal: localStorage.getItem('id_sucursal') || '',
      id_cliente: (pedido as unknown as { id_cliente: { id_cliente: string } }).id_cliente?.id_cliente || '',
      id_caja: (pedido as unknown as { id_caja?: string }).id_caja || '',
      id_vendedor: (pedido as unknown as { id_vendedor?: string }).id_vendedor || '',
      observaciones: pedido.observaciones || '',
    });
    if (pedido.detalles && Array.isArray(pedido.detalles)) {
      base.setDetalles(
        pedido.detalles.map((d: DetallePedido) => ({
          id_producto: (d as unknown as { id_producto: string }).id_producto || '',
          cantidad: String(d.cantidad ?? 0),
          precio_unitario: String(d.precio_unitario ?? 0),
          descuento_porcentaje: String((d as unknown as { descuento_porcentaje?: number }).descuento_porcentaje ?? ''),
          sku: (d as unknown as { sku?: string }).sku || '',
          producto: (d as unknown as { producto?: string }).producto || '',
        }))
      );
    }
    base.setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pedidoData, isLoadingPedido]);

  const submitPedido = async (pagosToSend?: Pago[]) => {
    base.setLoading(true);
    base.setError('');
    base.setSuccess('');

    if (!form.fecha_pedido || !form.id_empresa || !form.id_sucursal) {
      base.setError('Todos los campos obligatorios deben estar completos.');
      base.setLoading(false);
      return null;
    }
    if (base.detalles.length === 0) {
      base.setError('Debe agregar al menos un producto al pedido.');
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
      base.setError('Debe seleccionar un cliente antes de guardar el pedido.');
      base.setLoading(false);
      return null;
    }

    const detallesConSubtotal = base.detalles.map(d => ({
      ...d,
      subtotal: String(Number(d.cantidad) * Number(d.precio_unitario)),
    }));
    const payload: Record<string, unknown> = { ...form, id_cliente: idClienteFinal, detalles: detallesConSubtotal };
    delete payload.numero_pedido;

    try {
      let response: { id_pedido?: string; numero_pedido?: string };
      if (pedidoId) {
        response = await patch(`/ventas/pedidos/${pedidoId}/`, payload);
        base.setSuccess('Pedido actualizado exitosamente.');
      } else {
        response = await post('/ventas/pedidos/', payload);
        const numPedido = response?.numero_pedido || '';
        const idCreado = response?.id_pedido || '';
        setNumeroPedidoCreado(numPedido);
        base.setSuccess(`Pedido creado exitosamente${numPedido ? ` (N° ${numPedido})` : ''}.`);

        const pagosAEnviar = pagosToSend ?? base.pagos;
        if (pagosAEnviar.length > 0 && idCreado) {
          try {
            for (const pago of pagosAEnviar) {
              await pagosService.createPagoDocumento('PEDIDO', idCreado, pago);
            }
          } catch {
            base.setSuccess(`Pedido creado${numPedido ? ` (N° ${numPedido})` : ''}, pero hubo un error con los pagos.`);
          }
        }

        setForm(initialForm());
        base.setDetalles([]);
        base.setDetalleForm({ id_producto: '', cantidad: '', precio_unitario: '', descuento_porcentaje: '', sku: '', producto: '' });
        base.setPagos([]);
        base.setClienteManual({ razon_social: '', rif: '', telefono: '', direccion: '', correo: '', codigo_cliente: '' });
      }
      base.setLoading(false);
      return response?.numero_pedido || '';
    } catch {
      base.setError('Error al crear el pedido');
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
    numeroPedidoCreado,
    submitPedido,
    ...base,
    handleClienteManualKeyDown,
  };
};
