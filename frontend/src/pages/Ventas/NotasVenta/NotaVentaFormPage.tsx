import React, { useState } from 'react';
import type { Pago, NotaCredito } from '../../../components/Pedidos/ModalPago';
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
import { useNotaVentaForm } from '../../../hooks/useNotaVentaForm';
import type { Usuario } from '../../../services/users';
import type { Producto } from '../../../services/productosService';
import { pagosService } from '../../../services/pagosService';

const getFieldString = (obj: unknown, key: string) => {
  if (!obj || typeof obj !== 'object') return '';
  const v = (obj as Record<string, unknown>)[key];
  return v === undefined || v === null ? '' : String(v);
};

const NotaVentaFormPage: React.FC = () => {
  const navigate = useNavigate();
  const { id_nota_venta } = useParams<{ id_nota_venta: string }>();
  const isEditing = !!id_nota_venta;
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
    numeroNotaVentaCreado,
    sesionActiva,
    empresas,
    sucursales,
    setDescuentoGeneral,
    setPagos,
    handleChange,
    handleClienteManualChange,
    handleClienteManualKeyDown,
    handleClienteBlur,
    vendedores,
    handleDetalleChange,
    handleAddDetalle,
    handleRemoveDetalle,
    selectProducto,
    submitNotaVenta,
  } = useNotaVentaForm(id_nota_venta);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const result = await submitNotaVenta();
    if (result && isEditing) {
      // Después de editar, redirigir a la página de detalle
      navigate(`/ventas/notas-venta/${id_nota_venta}`);
    }
  };

  const handleEnviar = () => alert('Función Enviar: convertir en Factura Fiscal y cambiar estado a Enviado');
  const handlePagar = () => setShowPagoModal(true);
  const handleAnular = () => alert('Función Anular: cambiar estado a Anulado');
  const handleImprimir = () => alert('Función Imprimir: generar documento de nota de venta');

  const handleConfirmPago = (pagosConfirmados: Pago[], vueltos?: Pago[], notasCreditoUtilizadas?: NotaCredito[]) => {
    setShowPagoModal(false);
    if (pagosConfirmados?.length > 0) {
      // Almacenar pagos en el estado del hook para que se envíen automáticamente al guardar
      setPagos(pagosConfirmados);
      submitNotaVenta(pagosConfirmados).then(async (result) => {
        if (result) {
          // Procesar vueltos
          if (vueltos && vueltos.length > 0) {
            try {
              await pagosService.procesarVueltos(vueltos);
            } catch (error) {
              console.error('Error procesando vueltos:', error);
            }
          }
          // Conciliar notas de crédito
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
    <PageLayout>
      <Typography variant="h4" component="h2" gutterBottom>
        {isEditing ? 'Editar Nota de Venta' : 'Nueva Nota de Venta'}
      </Typography>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {success && <Alert severity="success" sx={{ mb: 2 }}>{success}</Alert>}

      <Paper sx={{ p: 3 }}>
        <form onSubmit={handleSubmit}>
          {/* Información del contexto */}
          <Box sx={{ mb: 3 }}>
            <Typography variant="h6" gutterBottom>
              Información de la Nota de Venta
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
                  <FormControl fullWidth>
                    <InputLabel id="empresa-label">Empresa</InputLabel>
                    <Select
                      labelId="empresa-label"
                      name="id_empresa"
                      value={form.id_empresa || ''}
                      label="Empresa"
                      onChange={(e) => handleChange(e as unknown as React.ChangeEvent<HTMLInputElement>)}
                    >
                      {empresas.map((emp) => (
                        <MenuItem key={emp.id_empresa} value={emp.id_empresa}>{emp.nombre_legal}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <FormControl fullWidth>
                    <InputLabel id="sucursal-label">Sucursal</InputLabel>
                    <Select
                      labelId="sucursal-label"
                      name="id_sucursal"
                      value={form.id_sucursal || ''}
                      label="Sucursal"
                      onChange={(e) => handleChange(e as unknown as React.ChangeEvent<HTMLInputElement>)}
                      disabled={!form.id_empresa}
                    >
                      {sucursales.map((suc) => (
                        <MenuItem key={suc.id_sucursal} value={suc.id_sucursal}>{suc.nombre}</MenuItem>
                      ))}
                    </Select>
                  </FormControl>
                  <TextField
                    label="Caja Física"
                    value="Sin sesión activa"
                    InputProps={{ readOnly: true }}
                  />
                </>
              )}
              <TextField
                label="ID Caja"
                value={sesionActiva?.caja_fisica_principal?.id_caja || form.id_caja || 'No disponible'}
                InputProps={{ readOnly: true }}
              />
              <TextField
                label="Usuario"
                value={sesionActiva?.usuario?.first_name && sesionActiva?.usuario?.last_name ? `${sesionActiva.usuario.first_name} ${sesionActiva.usuario.last_name}` : sesionActiva?.usuario?.username || 'No disponible'}
                InputProps={{ readOnly: true }}
              />
              <FormControl fullWidth>
                <InputLabel id="vendedor-label">Vendedor</InputLabel>
                <Select
                  labelId="vendedor-label"
                  name="id_vendedor"
                  value={form.id_vendedor || ''}
                  label="Vendedor"
                  onChange={(e) => handleChange(e as unknown as React.ChangeEvent<HTMLInputElement>)}
                >
                  {vendedores && vendedores.length > 0 ? (vendedores as Usuario[]).map((v) => (
                    <MenuItem key={v.id} value={String(v.id)}>{v.first_name && v.last_name ? `${v.first_name} ${v.last_name}` : v.username}</MenuItem>
                  )) : <MenuItem value="">Sin vendedores</MenuItem>}
                </Select>
              </FormControl>
              <TextField
                label="Número de Nota de Venta"
                value={numeroNotaVentaCreado || 'Calculando...'}
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
                <Typography variant="h6" gutterBottom>Preview de la Nota de Venta</Typography>
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
              name="observaciones"
              value={form.observaciones}
              onChange={handleChange}
            />
          </Box>

          {/* Botones */}
          <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap' }}>
            <Button type="submit" variant="contained" disabled={loading || !form.id_cliente}>
              {loading ? 'Guardando...' : 'Guardar Nota de Venta'}
            </Button>
            <Button type="button" variant="contained" color="secondary" onClick={() => navigate('/ventas/notas-venta')}>
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
        tipoDocumento="NOTA_VENTA"
        idDocumento={id_nota_venta || 'nuevo'}
        tipoOperacionInicial="INGRESO"
      />
    </PageLayout>
  );
}
export default NotaVentaFormPage;