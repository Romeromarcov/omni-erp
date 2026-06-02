import React, { useState } from 'react';
import { Controller } from 'react-hook-form';
import type { Pago, NotaCredito } from '../../../components/Pedidos/ModalPago';
import PageLayout from '../../../components/PageLayout';
import { useNavigate, useParams } from 'react-router-dom';
import './PedidoFormPage.css';
import ModalBusquedaProducto from '../../../components/Pedidos/ModalBusquedaProducto';
import ModalBusquedaCliente from '../../../components/Pedidos/ModalBusquedaCliente';
import TablaProductos from '../../../components/Pedidos/TablaProductos';
import ResumenTotales from '../../../components/Pedidos/ResumenTotales';
import FormularioProducto from '../../../components/Pedidos/FormularioProducto';
import FormularioCliente from '../../../components/Pedidos/FormularioCliente';
import ModalPago from '../../../components/Pedidos/ModalPago';
import { Alert, Box, Button, FormControl, InputLabel, MenuItem, Paper, Select, TextField, Typography } from '@mui/material';
import { usePedidoForm } from '../../../hooks/usePedidoForm';
import type { Usuario } from '../../../services/users';
import type { Producto } from '../../../services/productosService';
import { pagosService } from '../../../services/pagosService';
import { useSnackbar } from '../../../contexts/feedbackTypes';

const getFieldString = (obj: unknown, key: string) => {
  if (!obj || typeof obj !== 'object') return '';
  const v = (obj as Record<string, unknown>)[key];
  return v === undefined || v === null ? '' : String(v);
};

const PedidoFormPage: React.FC = () => {
  const navigate = useNavigate();
  const snackbar = useSnackbar();
  const { id_pedido } = useParams<{ id_pedido: string }>();
  const isEditing = !!id_pedido;
  const [showClienteModal, setShowClienteModal] = useState(false);
  const [showProductoModal, setShowProductoModal] = useState(false);
  const [showPagoModal, setShowPagoModal] = useState(false);

  const {
    control,
    register,
    handleSubmit,
    watch,
    getValues,
    error,
    success,
    loading,
    productos,
    detalleForm,
    descuentoGeneral,
    clienteManual,
    numeroPedidoCreado,
    sesionActiva,
    empresas,
    sucursales,
    setDescuentoGeneral,
    setPagos,
    handleClienteManualChange,
    handleClienteManualKeyDown,
    handleClienteBlur,
    vendedores,
    handleDetalleChange,
    handleAddDetalle,
    handleRemoveDetalle,
    selectProducto,
    setClienteId,
    submitPedido,
  } = usePedidoForm(id_pedido);

  const detalles = watch('detalles') || [];
  const idCliente = watch('id_cliente');
  const idEmpresa = watch('id_empresa');
  const idCaja = watch('id_caja');

  const onSubmit = handleSubmit(async (values) => {
    const result = await submitPedido(values);
    if (result && isEditing) {
      navigate(`/ventas/pedidos/${id_pedido}`);
    }
  });

  const handleEnviar = () => snackbar.info('Función Enviar: convertir en Nota de venta y cambiar estado a Enviado');
  const handlePagar = () => setShowPagoModal(true);
  const handleAnular = () => snackbar.info('Función Anular: cambiar estado a Anulado');
  const handleImprimir = () => snackbar.info('Función Imprimir: generar documento de pedido');

  const handleConfirmPago = (pagosConfirmados: Pago[], vueltos?: Pago[], notasCreditoUtilizadas?: NotaCredito[]) => {
    setShowPagoModal(false);
    if (pagosConfirmados?.length > 0) {
      setPagos(pagosConfirmados);
      submitPedido(getValues(), pagosConfirmados).then(async (result) => {
        if (result) {
          if (vueltos && vueltos.length > 0) {
            try {
              await pagosService.procesarVueltos(vueltos);
            } catch (error) {
              console.error('Error procesando vueltos:', error);
            }
          }
          if (notasCreditoUtilizadas && notasCreditoUtilizadas.length > 0) {
            try {
              await pagosService.conciliarNotasCredito(notasCreditoUtilizadas, id_pedido || 'nuevo', 'PEDIDO');
            } catch (error) {
              console.error('Error conciliando notas de crédito:', error);
            }
          }
        }
      });
    }
  };

  return (
    <PageLayout>
      <Typography variant="h4" component="h2" gutterBottom>
        {isEditing ? 'Editar Pedido' : 'Nuevo Pedido'}
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

      <Paper sx={{ p: 3 }}>
        <form onSubmit={onSubmit} noValidate>
          {/* Información del contexto */}
          <Box sx={{ mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              Información del Pedido
            </Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 2 }}>
              {sesionActiva ? (
                <>
                  <TextField
                    label="Empresa"
                    value={sesionActiva.caja_fisica_principal?.sucursal?.empresa?.nombre || 'No disponible'}
                    InputProps={{ readOnly: true }}
                  />
                  <TextField
                    label="Sucursal"
                    value={sesionActiva.caja_fisica_principal?.sucursal?.nombre || 'No disponible'}
                    InputProps={{ readOnly: true }}
                  />
                  <TextField
                    label="Caja Física"
                    value={sesionActiva.caja_fisica_principal?.nombre || 'No disponible'}
                    InputProps={{ readOnly: true }}
                  />
                </>
              ) : (
                <>
                  <Controller
                    name="id_empresa"
                    control={control}
                    render={({ field }) => (
                      <FormControl fullWidth>
                        <InputLabel id="empresa-label">Empresa</InputLabel>
                        <Select labelId="empresa-label" label="Empresa" {...field} value={field.value || ''}>
                          {empresas.map((emp) => (
                            <MenuItem key={emp.id_empresa} value={emp.id_empresa}>{emp.nombre_legal}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    )}
                  />
                  <Controller
                    name="id_sucursal"
                    control={control}
                    render={({ field }) => (
                      <FormControl fullWidth>
                        <InputLabel id="sucursal-label">Sucursal</InputLabel>
                        <Select labelId="sucursal-label" label="Sucursal" {...field} value={field.value || ''} disabled={!idEmpresa}>
                          {sucursales.map((suc) => (
                            <MenuItem key={suc.id_sucursal} value={suc.id_sucursal}>{suc.nombre}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    )}
                  />
                  <TextField
                    label="Caja Física"
                    value="Sin sesión activa"
                    InputProps={{ readOnly: true }}
                  />
                </>
              )}
              <TextField
                label="ID Caja"
                value={sesionActiva?.caja_fisica_principal?.id_caja || idCaja || 'No disponible'}
                InputProps={{ readOnly: true }}
              />
              <TextField
                label="Usuario"
                value={sesionActiva?.usuario?.first_name && sesionActiva?.usuario?.last_name ? `${sesionActiva.usuario.first_name} ${sesionActiva.usuario.last_name}` : sesionActiva?.usuario?.username || 'No disponible'}
                InputProps={{ readOnly: true }}
              />
              <Controller
                name="id_vendedor"
                control={control}
                render={({ field }) => (
                  <FormControl fullWidth>
                    <InputLabel id="vendedor-label">Vendedor</InputLabel>
                    <Select labelId="vendedor-label" label="Vendedor" {...field} value={field.value || ''}>
                      {vendedores && vendedores.length > 0 ? (vendedores as Usuario[]).map((v) => (
                        <MenuItem key={v.id} value={String(v.id)}>{v.first_name && v.last_name ? `${v.first_name} ${v.last_name}` : v.username}</MenuItem>
                      )) : <MenuItem value="">Sin vendedores</MenuItem>}
                    </Select>
                  </FormControl>
                )}
              />
              <TextField
                label="Número de Pedido"
                value={numeroPedidoCreado || 'Calculando...'}
                InputProps={{ readOnly: true }}
              />
            </Box>
          </Box>

          {/* Cliente */}
          <Box sx={{ mb: 3 }}>
            <Typography variant="h6" gutterBottom>Cliente</Typography>
            <FormularioCliente
              clienteManual={clienteManual}
              onChange={handleClienteManualChange}
              onKeyDown={handleClienteManualKeyDown}
              onBlur={handleClienteBlur}
              onBuscar={() => setShowClienteModal(true)}
            />
          </Box>

          {/* Productos */}
          <Box sx={{ mb: 3 }}>
            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
              <Typography variant="h6">Productos</Typography>
              <Button type="button" variant="outlined" onClick={() => setShowProductoModal(true)}>
                Buscar producto
              </Button>
            </Box>
            <FormularioProducto
              productos={productos}
              detalleForm={detalleForm}
              onChange={handleDetalleChange}
              onAdd={handleAddDetalle}
            />

            {/* Preview de productos */}
            {detalles.length > 0 && (
              <Box sx={{ mt: 3 }}>
                <Typography variant="h6" gutterBottom>Preview del Pedido</Typography>
                <TablaProductos detalles={detalles} productos={productos} onRemove={handleRemoveDetalle} />
                <ResumenTotales detalles={detalles} descuentoGeneral={descuentoGeneral} setDescuentoGeneral={setDescuentoGeneral} />
              </Box>
            )}
          </Box>

          {/* Observaciones */}
          <Box sx={{ mb: 3 }}>
            <TextField
              fullWidth
              label="Observaciones"
              multiline
              rows={3}
              {...register('observaciones')}
            />
          </Box>

          {/* Botones */}
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <Button type="submit" variant="contained" disabled={loading || !idCliente}>
              {loading ? 'Guardando...' : 'Guardar Pedido'}
            </Button>
            <Button type="button" variant="contained" color="secondary" onClick={() => navigate('/ventas/pedidos')}>
              Cancelar
            </Button>
            <Button type="button" variant="outlined" onClick={handlePagar}>Pagar</Button>
            {isEditing && (
              <>
                <Button type="button" variant="outlined" onClick={handleEnviar}>Enviar</Button>
                <Button type="button" variant="outlined" onClick={handleAnular}>Anular</Button>
                <Button type="button" variant="outlined" onClick={handleImprimir}>Imprimir</Button>
              </>
            )}
          </Box>
        </form>
      </Paper>
      <ModalBusquedaCliente
        open={showClienteModal}
        idEmpresa={idEmpresa || localStorage.getItem('id_empresa') || ''}
        onSelect={cli => {
          setClienteId(cli.id_cliente);
          handleClienteManualChange({ target: { name: 'razon_social', value: cli.razon_social || '' } } as React.ChangeEvent<HTMLInputElement>);
          handleClienteManualChange({ target: { name: 'rif', value: cli.rif || '' } } as React.ChangeEvent<HTMLInputElement>);
          handleClienteManualChange({ target: { name: 'telefono', value: cli.telefono || '' } } as React.ChangeEvent<HTMLInputElement>);
          handleClienteManualChange({ target: { name: 'direccion', value: getFieldString(cli, 'direccion') || getFieldString(cli, 'direccion_fiscal') } } as React.ChangeEvent<HTMLInputElement>);
          handleClienteManualChange({ target: { name: 'correo', value: getFieldString(cli, 'email') || getFieldString(cli, 'correo') } } as React.ChangeEvent<HTMLInputElement>);
          handleClienteManualChange({ target: { name: 'codigo_cliente', value: getFieldString(cli, 'codigo_cliente') } } as React.ChangeEvent<HTMLInputElement>);
          setShowClienteModal(false);
        }}
        onClose={() => setShowClienteModal(false)}
      />
      <ModalBusquedaProducto
        open={showProductoModal}
        productos={productos}
        onSelect={(prod: Producto) => {
          selectProducto(prod);
          setShowProductoModal(false);
        }}
        onClose={() => setShowProductoModal(false)}
      />
      <ModalPago
        open={showPagoModal}
        monto={Number(detalles.reduce((acc: number, d: { precio_unitario?: string; cantidad?: string }) => acc + Number(d.precio_unitario || 0) * Number(d.cantidad || 0), 0))}
        onClose={() => setShowPagoModal(false)}
        onConfirm={handleConfirmPago}
        empresaId={idEmpresa || localStorage.getItem('id_empresa') || ''}
        tipoDocumento="PEDIDO"
        idDocumento={id_pedido || 'nuevo'}
        tipoOperacionInicial="INGRESO"
      />
    </PageLayout>
  );
}
export default PedidoFormPage;
