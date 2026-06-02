import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { NotaVenta, DetalleNotaVenta } from '../types/ventas';
import { get } from '../services/api';
import { pagosService } from '../services/pagosService';
import { getEmpresaId } from '../utils/empresa';
import type { Pago } from '../components/Pedidos/ModalPago';
import { NotaVentaService } from '../services/ventas';
import { useDocumentoVentaBase } from './useDocumentoVentaBase';
import { notaVentaFormSchema, type NotaVentaFormInput } from '../schemas/ventas.schemas';

const notaVentaService = new NotaVentaService();

const initialForm = (): NotaVentaFormInput => ({
  numero_nota_venta: '',
  fecha_emision: new Date().toISOString().slice(0, 10),
  id_empresa: getEmpresaId() || '',
  id_sucursal: localStorage.getItem('id_sucursal') || '',
  id_cliente: '',
  id_caja: '',
  id_vendedor: '',
  observaciones: '',
  detalles: [],
});

export const useNotaVentaForm = (notaVentaId?: string) => {
  const [numeroNotaVentaCreado, setNumeroNotaVentaCreado] = useState<string | null>(null);

  const base = useDocumentoVentaBase<NotaVentaFormInput>({
    schema: notaVentaFormSchema,
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

  const { data: notaData, isLoading: isLoadingNota } = useQuery({
    queryKey: ['notas-venta', notaVentaId],
    queryFn: () => get(`/ventas/notas-venta/${notaVentaId}/`) as Promise<NotaVenta>,
    enabled: !!notaVentaId,
  });

  useEffect(() => {
    if (isLoadingNota) { base.setLoading(true); return; }
    if (!notaData) { base.setLoading(false); return; }
    if (base.formState.isDirty) { base.setLoading(false); return; }
    const nota = notaData;
    base.reset({
      numero_nota_venta: nota.numero_nota_venta || '',
      fecha_emision: (nota.fecha_emision || nota.fecha_nota_venta || '').slice(0, 10) || new Date().toISOString().slice(0, 10),
      id_empresa: nota.id_empresa || getEmpresaId() || '',
      id_sucursal: localStorage.getItem('id_sucursal') || '',
      id_cliente: nota.id_cliente?.id_cliente || '',
      id_caja: nota.id_caja || '',
      id_vendedor: nota.id_vendedor || '',
      observaciones: nota.observaciones || '',
      detalles: Array.isArray(nota.detalles)
        ? nota.detalles.map((d: DetalleNotaVenta) => ({
            id_producto: d.id_producto || '',
            cantidad: String(d.cantidad ?? 0),
            precio_unitario: String(d.precio_unitario ?? 0),
            descuento_porcentaje: '',
            sku: '',
            producto: '',
            comentarios: '',
          }))
        : [],
    });
    base.setLoading(false);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [notaData, isLoadingNota]);

  const submitNotaVenta = async (values: NotaVentaFormInput, pagosToSend?: Pago[]) => {
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
      subtotal: Number(d.cantidad) * Number(d.precio_unitario),
    }));
    const payload: Record<string, unknown> = {
      ...values,
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

        base.reset(initialForm());
        base.resetAuxState();
      }
      base.setLoading(false);
      return response?.numero_nota_venta || '';
    } catch {
      base.setError('Error al crear la nota de venta');
      base.setLoading(false);
      return null;
    }
  };

  const handleClienteManualKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) =>
    void base.handleClienteManualKeyDown(e, base.setClienteId);

  return {
    ...base,
    numeroNotaVentaCreado,
    submitNotaVenta,
    handleClienteManualKeyDown,
  };
};
