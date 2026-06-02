import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { Pedido, DetallePedido } from '../types/ventas';
import { post, get, patch } from '../services/api';
import { pagosService } from '../services/pagosService';
import { getEmpresaId } from '../utils/empresa';
import type { Pago } from '../components/Pedidos/ModalPago';
import { useDocumentoVentaBase } from './useDocumentoVentaBase';
import { subtotalLinea, toFixedStr } from '../lib/decimal';
import { pedidoFormSchema, type PedidoFormInput } from '../schemas/ventas.schemas';

const initialForm = (): PedidoFormInput => ({
  numero_pedido: '',
  fecha_pedido: new Date().toISOString().slice(0, 10),
  id_empresa: getEmpresaId() || '',
  id_sucursal: localStorage.getItem('id_sucursal') || '',
  id_cliente: '',
  id_caja: '',
  id_vendedor: '',
  observaciones: '',
  detalles: [],
});

export const usePedidoForm = (pedidoId?: string) => {
  const [numeroPedidoCreado, setNumeroPedidoCreado] = useState<string | null>(null);

  const base = useDocumentoVentaBase<PedidoFormInput>({
    schema: pedidoFormSchema,
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

  const { data: pedidoData, isLoading: isLoadingPedido } = useQuery({
    queryKey: ['pedidos', pedidoId],
    queryFn: () => get(`/ventas/pedidos/${pedidoId}/`) as Promise<Pedido>,
    enabled: !!pedidoId,
  });

  useEffect(() => {
    if (isLoadingPedido) { base.setLoading(true); return; }
    if (!pedidoData) { base.setLoading(false); return; }
    if (base.formState.isDirty) { base.setLoading(false); return; }
    const pedido = pedidoData;
    base.reset({
      numero_pedido: pedido.numero_pedido || '',
      fecha_pedido: pedido.fecha_pedido?.slice(0, 10) ?? new Date().toISOString().slice(0, 10),
      id_empresa: pedido.id_empresa || getEmpresaId() || '',
      id_sucursal: localStorage.getItem('id_sucursal') || '',
      id_cliente: pedido.id_cliente?.id_cliente || '',
      id_caja: pedido.id_caja || '',
      id_vendedor: pedido.id_vendedor || '',
      observaciones: pedido.observaciones || '',
      detalles: Array.isArray(pedido.detalles)
        ? pedido.detalles.map((d: DetallePedido) => ({
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
  }, [pedidoData, isLoadingPedido]);

  const submitPedido = async (values: PedidoFormInput, pagosToSend?: Pago[]) => {
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

    // FE-HIGH-7: subtotal con aritmética decimal (no Number()*Number()).
    const detallesConSubtotal = values.detalles.map(d => ({
      ...d,
      subtotal: toFixedStr(subtotalLinea(d.cantidad, d.precio_unitario)),
    }));
    const payload: Record<string, unknown> = { ...values, id_cliente: idClienteFinal, detalles: detallesConSubtotal };
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

        base.reset(initialForm());
        base.resetAuxState();
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
    void base.handleClienteManualKeyDown(e, base.setClienteId);

  return {
    ...base,
    numeroPedidoCreado,
    submitPedido,
    handleClienteManualKeyDown,
  };
};
