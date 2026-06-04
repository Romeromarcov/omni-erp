import React, { useState } from 'react';
import { Controller } from 'react-hook-form';
import type { Pago, NotaCredito } from '../../../components/Pedidos/ModalPago';
import { useNavigate, useParams } from 'react-router-dom';
import ModalBusquedaProducto from '../../../components/Pedidos/ModalBusquedaProducto';
import ModalBusquedaCliente from '../../../components/Pedidos/ModalBusquedaCliente';
import TablaProductos from '../../../components/Pedidos/TablaProductos';
import ResumenTotales from '../../../components/Pedidos/ResumenTotales';
import FormularioProducto from '../../../components/Pedidos/FormularioProducto';
import FormularioCliente from '../../../components/Pedidos/FormularioCliente';
import ModalPago from '../../../components/Pedidos/ModalPago';
import { Alert, Box, Button, Card, FormControl, InputLabel, MenuItem, Select, TextField } from '@mui/material';
import { useNotaVentaForm } from '../../../hooks/useNotaVentaForm';
import type { Usuario } from '../../../services/users';
import type { Producto } from '../../../services/productosService';
import { pagosService } from '../../../services/pagosService';
import { useSnackbar } from '../../../contexts/feedbackTypes';
import { PageContainer, PageHeader, SectionTitle } from '../../../components/ui';

const getFieldString = (obj: unknown, key: string) => {
  if (!obj || typeof obj !== 'object') return '';
  const v = (obj as Record<string, unknown>)[key];
  return v === undefined || v === null ? '' : String(v);
};

const NotaVentaFormPage: React.FC = () => {
  const navigate = useNavigate();
  const snackbar = useSnackbar();
  const { id_nota_venta } = useParams<{ id_nota_venta: string }>();
  const isEditing = !!id_nota_venta;
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
    numeroNotaVentaCreado,
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
    submitNotaVenta,
  } = useNotaVentaForm(id_nota_venta);

  const detalles = watch('detalles') || [];
  const idCliente = watch('id_cliente');
  const idEmpresa = watch('id_empresa');
  const idCaja = watch('id_caja');

  const onSubmit = handleSubmit(async (values) => {
    const result = await submitNotaVenta(values);
    if (result && isEditing) {
      navigate(`/ventas/notas-venta/${id_nota_venta}`);
    }
  });

  const handleEnviar = () => snackbar.info('Función Enviar: convertir en Factura Fiscal y cambiar estado a Enviado');
  const handlePagar = () => setShowPagoModal(true);
  const handleAnular = () => snackbar.info('Función Anular: cambiar estado a Anulado');
  const handleImprimir = () => snackbar.info('Función Imprimir: generar documento de nota de venta');

  const handleConfirmPago = (pagosConfirmados: Pago[], vueltos?: Pago[], notasCreditoUtilizadas?: NotaCredito[]) => {
    setShowPagoModal(false);
    if (pagosConfirmados?.length > 0) {
      setPagos(pagosConfirmados);
      submitNotaVenta(getValues(), pagosConfirmados).then(async (result) => {
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
              await pagosService.conciliarNotasCredito(notasCreditoUtilizadas, id_nota_venta || 'nuevo', 'NOTA_VENTA');
            } catch (error) {
              console.error('Error conciliando notas de crédito:', error);
            }
          }
        }
      });
    }
  };

  return (
    <PageContainer maxWidth={900}>
      <PageHeader
        title={isEditing ? 'Editar Nota de Venta' : 'Nueva Nota de Venta'}
        actions={
          <Button variant="outlined" color="secondary" onClick={() => navigate('/ventas/notas-venta')}>
            Cancelar
          </Button>
        }
      />

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

      <Card sx={{ p: { xs: 2, md: 3 } }}>
        <form onSubmit={onSubmit} noValidate>
          {/* Información del contexto */}
          <Box sx={{ mb: 3 }}>
            <SectionTitle>Información de la Nota de Venta</SectionTitle>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2,1fr)', md: 'repeat(auto-fit,minmax(280px,1fr))' }, gap: 2 }}>
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
                label="Número de Nota de Venta"
                value={numeroNotaVentaCreado || 'Calculando...'}
                InputProps={{ readOnly: true }}
              />
            </Box>
          </Box>

          {/* Cliente */}
          <Box sx={{ mb: 3 }}>
            <SectionTitle>Cliente</SectionTitle>
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
            <SectionTitle action={
              <Button type="button" variant="outlined" size="small" onClick={() => setShowProductoModal(true)}>
                Buscar producto
              </Button>
            }>Productos</SectionTitle>
            <FormularioProducto
              productos={productos}
              detalleForm={detalleForm}
              onChange={handleDetalleChange}
              onAdd={handleAddDetalle}
            />

            {/* Preview de productos */}
            {detalles.length > 0 && (
              <Box sx={{ mt: 3 }}>
                <SectionTitle>Preview de la Nota de Venta</SectionTitle>
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
            <Button type="submit" variant="contained" disabled={loading || !idCliente}
              sx={{ flex: { xs: '1 1 100%', sm: 'initial' } }}>
              {loading ? 'Guardando...' : 'Guardar Nota de Venta'}
            </Button>
            <Button type="button" variant="outlined" onClick={handlePagar}
              sx={{ flex: { xs: '1 1 100%', sm: 'initial' } }}>Pagar</Button>
            {isEditing && (
              <>
                <Button type="button" variant="outlined" onClick={handleEnviar}>Enviar</Button>
                <Button type="button" variant="outlined" onClick={handleAnular}>Anular</Button>
                <Button type="button" variant="outlined" onClick={handleImprimir}>Imprimir</Button>
              </>
            )}
          </Box>
        </form>
      </Card>

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
        tipoDocumento="NOTA_VENTA"
        idDocumento={id_nota_venta || 'nuevo'}
        tipoOperacionInicial="INGRESO"
      />
    </PageContainer>
  );
};

export default NotaVentaFormPage;
