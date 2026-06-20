import React, { useState } from 'react';
import { Controller } from 'react-hook-form';
import { D, sumDecimals } from '../../../lib/decimal';
import { useNavigate, useParams } from 'react-router-dom';
import ModalBusquedaProducto from '../../../components/Pedidos/ModalBusquedaProducto';
import ModalBusquedaCliente from '../../../components/Pedidos/ModalBusquedaCliente';
import TablaProductos from '../../../components/Pedidos/TablaProductos';
import ResumenTotales from '../../../components/Pedidos/ResumenTotales';
import FormularioProducto from '../../../components/Pedidos/FormularioProducto';
import FormularioCliente from '../../../components/Pedidos/FormularioCliente';
import ModalPago from '../../../components/Pedidos/ModalPago';
import { Alert, Box, Button, Card, FormControl, InputLabel, MenuItem, Select, TextField } from '@mui/material';
import { useCotizacionForm } from '../../../hooks/useCotizacionForm';
import type { Producto } from '../../../services/productosService';
import { useSnackbar } from '../../../contexts/feedbackTypes';
import { PageContainer, PageHeader, SectionTitle } from '../../../components/ui';

const getFieldString = (obj: unknown, key: string) => {
  // Object.hasOwn limita la lectura a propiedades propias (nunca la cadena
  // de prototipos) y Reflect.get evita el acceso computado obj[key] (CTF-006).
  if (!obj || typeof obj !== 'object' || !Object.hasOwn(obj, key)) return '';
  const v: unknown = Reflect.get(obj, key);
  return v === undefined || v === null ? '' : String(v);
};

const CotizacionFormPage: React.FC = () => {
  const navigate = useNavigate();
  const snackbar = useSnackbar();
  const { id } = useParams<{ id: string }>();
  const isEditing = !!id && id !== 'new';
  const [showClienteModal, setShowClienteModal] = useState(false);
  const [showProductoModal, setShowProductoModal] = useState(false);
  const [showPagoModal, setShowPagoModal] = useState(false);

  const {
    control,
    register,
    handleSubmit,
    watch,
    error,
    success,
    loading,
    productos,
    detalleForm,
    descuentoGeneral,
    clienteManual,
    sesionActiva,
    empresas,
    setDescuentoGeneral,
    handleClienteManualChange,
    handleClienteManualKeyDown,
    handleClienteBlur,
    handleDetalleChange,
    handleAddDetalle,
    handleRemoveDetalle,
    selectProducto,
    setClienteId,
    submitCotizacion,
  } = useCotizacionForm(id);

  const detalles = watch('detalles') || [];
  const idCliente = watch('id_cliente');
  const idEmpresa = watch('id_empresa');

  const onSubmit = handleSubmit(async (values) => {
    await submitCotizacion(values);
  });

  const handleEnviar = () => snackbar.info('Función Enviar: convertir en Nota de venta y cambiar estado a Enviado');
  const handlePagar = () => setShowPagoModal(true);
  const handleAnular = () => snackbar.info('Función Anular: cambiar estado a Anulado');
  const handleImprimir = () => snackbar.info('Función Imprimir: generar documento de cotización');
  const handleConfirmPago = () => {
    setShowPagoModal(false);
  };

  return (
    <PageContainer maxWidth={900}>
      <PageHeader
        title={isEditing ? 'Editar Cotización' : 'Nueva Cotización'}
        actions={
          <Button variant="outlined" color="secondary" onClick={() => navigate('/ventas/cotizaciones')}>
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
            <SectionTitle>Información de la Cotización</SectionTitle>
            <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2,1fr)', md: 'repeat(auto-fit,minmax(280px,1fr))' }, gap: 2 }}>
              {sesionActiva ? (
                <>
                  <TextField label="Empresa" value={sesionActiva.caja_fisica_principal?.sucursal?.empresa?.nombre || 'No disponible'} InputProps={{ readOnly: true }} />
                  <TextField label="Sucursal" value={sesionActiva.caja_fisica_principal?.sucursal?.nombre || 'No disponible'} InputProps={{ readOnly: true }} />
                  <TextField label="Caja Física" value={sesionActiva.caja_fisica_principal?.nombre || 'No disponible'} InputProps={{ readOnly: true }} />
                </>
              ) : (
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
              )}
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
                <SectionTitle>Preview de la Cotización</SectionTitle>
                <TablaProductos detalles={detalles} productos={productos} onRemove={handleRemoveDetalle} />
                <ResumenTotales detalles={detalles} descuentoGeneral={descuentoGeneral} setDescuentoGeneral={setDescuentoGeneral} />
              </Box>
            )}
          </Box>

          {/* Observaciones */}
          <Box sx={{ mb: 3 }}>
            <TextField fullWidth label="Observaciones" multiline rows={3} {...register('observaciones')} />
          </Box>

          {/* Condiciones comerciales */}
          <Box sx={{ mb: 3 }}>
            <TextField fullWidth label="Condiciones Comerciales" multiline rows={3} {...register('condiciones_comerciales')} />
          </Box>

          {/* Botones */}
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <Button type="submit" variant="contained" disabled={loading || !idCliente}
              sx={{ flex: { xs: '1 1 100%', sm: 'initial' } }}>
              {loading ? 'Guardando...' : 'Guardar Cotización'}
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

      {/* Modales */}
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
        monto={sumDecimals(detalles.map((d: { precio_unitario?: string; cantidad?: string }) => D(d.precio_unitario).times(D(d.cantidad)))).toNumber()}
        onClose={() => setShowPagoModal(false)}
        onConfirm={handleConfirmPago}
        empresaId={idEmpresa || localStorage.getItem('id_empresa') || ''}
        tipoDocumento="COTIZACION"
        idDocumento={id || 'nuevo'}
        tipoOperacionInicial="INGRESO"
      />
    </PageContainer>
  );
};

export default CotizacionFormPage;
