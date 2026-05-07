import React, { useState } from 'react';
// Removed unused Pago, NotaCredito import
import PageLayout from '../../../components/PageLayout';
import { useNavigate, useParams } from 'react-router-dom';
import ModalBusquedaProducto from '../../../components/Pedidos/ModalBusquedaProducto';
import ModalBusquedaCliente from '../../../components/Pedidos/ModalBusquedaCliente';
import TablaProductos from '../../../components/Pedidos/TablaProductos';
import ResumenTotales from '../../../components/Pedidos/ResumenTotales';
import FormularioProducto from '../../../components/Pedidos/FormularioProducto';
import FormularioCliente from '../../../components/Pedidos/FormularioCliente';
import ModalPago from '../../../components/Pedidos/ModalPago';
import { Alert, Box, Button, FormControl, InputLabel, MenuItem, Paper, Select, TextField, Typography } from '@mui/material';
import { useCotizacionForm } from '../../../hooks/useCotizacionForm';
import type { Producto } from '../../../services/productosService';
// Removed unused pagosService import

const getFieldString = (obj: unknown, key: string) => {
  if (!obj || typeof obj !== 'object') return '';
  const v = (obj as Record<string, unknown>)[key];
  return v === undefined || v === null ? '' : String(v);
};

const CotizacionFormPage: React.FC = () => {
  const navigate = useNavigate();
  const { id } = useParams<{ id: string }>();
  const isEditing = !!id && id !== 'new';
  const [showClienteModal, setShowClienteModal] = useState(false);
  const [showProductoModal, setShowProductoModal] = useState(false);
  const [showPagoModal, setShowPagoModal] = useState(false);

  const {
    form,
    error,
    success,
    loading,
    productos,
    detalles,
    detalleForm,
    descuentoGeneral,
    clienteManual,
    sesionActiva,
    empresas,
    setDescuentoGeneral,
    handleChange,
    handleClienteManualChange,
    handleClienteManualKeyDown,
    handleClienteBlur,
    handleDetalleChange,
    handleAddDetalle,
    handleRemoveDetalle,
    selectProducto,
    submitCotizacion,
  } = useCotizacionForm(id);

  // Handlers for form actions
  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    await submitCotizacion();
  };
  const handleEnviar = () => alert('Función Enviar: convertir en Nota de venta y cambiar estado a Enviado');
  const handlePagar = () => setShowPagoModal(true);
  const handleAnular = () => alert('Función Anular: cambiar estado a Anulado');
  const handleImprimir = () => alert('Función Imprimir: generar documento de cotización');
  const handleConfirmPago = () => {
    setShowPagoModal(false);
    // Implementar lógica de confirmación de pago si es necesario
  };

  return (
    <PageLayout>
      <Typography variant="h4" component="h2" gutterBottom>
        {isEditing ? 'Editar Cotización' : 'Nueva Cotización'}
      </Typography>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}
      <Paper sx={{ p: 3 }}>
        <form onSubmit={handleSubmit}>
          {/* Información del contexto */}
          <Box sx={{ mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              Información de la Cotización
            </Typography>
            <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: 2 }}>
              {sesionActiva ? (
                <>
                  <TextField label="Empresa" value={sesionActiva.caja_fisica_principal?.sucursal?.empresa?.nombre || 'No disponible'} InputProps={{ readOnly: true }} />
                  <TextField label="Sucursal" value={sesionActiva.caja_fisica_principal?.sucursal?.nombre || 'No disponible'} InputProps={{ readOnly: true }} />
                  <TextField label="Caja Física" value={sesionActiva.caja_fisica_principal?.nombre || 'No disponible'} InputProps={{ readOnly: true }} />
                </>
              ) : (
                <>
                  <FormControl fullWidth>
                    <InputLabel id="empresa-label">Empresa</InputLabel>
                    <Select labelId="empresa-label" name="id_empresa" value={form.id_empresa || ''} label="Empresa" onChange={(e) => handleChange(e as unknown as React.ChangeEvent<HTMLInputElement>)}>
                      {empresas.map((emp) => (
                        <MenuItem key={emp.id_empresa} value={emp.id_empresa}>{emp.nombre_legal}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  {/* Si tienes sucursales, agrega aquí el selector de sucursal igual que en Pedido */}
                </>
              )}
              {/* Si tienes ID Caja, Usuario, Vendedor y Numeración, agrégalos aquí igual que en Pedido */}
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
                <Typography variant="h6" gutterBottom>Preview de la Cotización</Typography>
                <TablaProductos detalles={detalles} productos={productos} onRemove={handleRemoveDetalle} />
                <ResumenTotales detalles={detalles} descuentoGeneral={descuentoGeneral} setDescuentoGeneral={setDescuentoGeneral} />
              </Box>
            )}
          </Box>

          {/* Observaciones */}
          <Box sx={{ mb: 3 }}>
            <TextField fullWidth label="Observaciones" multiline rows={3} name="observaciones" value={form.observaciones} onChange={handleChange} />
          </Box>

          {/* Condiciones comerciales */}
          <Box sx={{ mb: 3 }}>
            <TextField fullWidth label="Condiciones Comerciales" multiline rows={3} name="condiciones_comerciales" value={form.condiciones_comerciales} onChange={handleChange} />
          </Box>

          {/* Botones */}
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <Button type="submit" variant="contained" disabled={loading || !form.id_cliente}>
              {loading ? 'Guardando...' : 'Guardar Cotización'}
            </Button>
            <Button type="button" variant="contained" color="secondary" onClick={() => navigate('/ventas/cotizaciones')}>
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
      {/* Modales */}
      <ModalBusquedaCliente
        open={showClienteModal}
        idEmpresa={form.id_empresa || localStorage.getItem('id_empresa') || ''}
        onSelect={cli => {
          handleChange({ target: { name: 'id_cliente', value: cli.id_cliente } } as React.ChangeEvent<HTMLInputElement>);
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
        empresaId={form.id_empresa || localStorage.getItem('id_empresa') || ''}
        tipoDocumento="COTIZACION"
        idDocumento={id || 'nuevo'}
        tipoOperacionInicial="INGRESO"
      />
    </PageLayout>
  );
};

export default CotizacionFormPage;