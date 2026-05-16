import React, { useState } from 'react';
import ModalBusqueda from '../ModalBusqueda';
import type { Producto } from '../../services/productosService';
import { Box, Button, Typography } from '@mui/material';

interface ModalBusquedaProductoProps {
  open: boolean;
  productos: Producto[];
  onSelect: (prod: Producto) => void;
  onClose: () => void;
}

const ModalBusquedaProducto: React.FC<ModalBusquedaProductoProps> = ({ open, productos, onSelect, onClose }) => {
  const [busqueda, setBusqueda] = useState('');
  const resultados = busqueda
    ? productos.filter(p => p.nombre_producto.toLowerCase().includes(busqueda.trim().toLowerCase()))
    : productos;

  const handleEnterKey = () => {
    if (resultados.length > 0) {
      onSelect(resultados[0]);
      onClose();
    }
  };

  return (
    <ModalBusqueda
      open={open}
      title="Buscar producto"
      inputPlaceholder="Buscar por nombre..."
      inputValue={busqueda}
      onInputChange={setBusqueda}
      items={resultados}
      onEnterKey={handleEnterKey}
      renderItem={(prod, close) => (
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%' }}>
          <Box>
            <Typography variant="body1" fontWeight="medium">
              {prod.nombre_producto}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              SKU: {prod.sku} | Precio: {typeof prod.precio_venta_sugerido === 'number' ? prod.precio_venta_sugerido.toFixed(2) : 'N/A'}
            </Typography>
          </Box>
          <Button
            type="button"
            variant="contained"
            size="small"
            onClick={(e) => {
              e.stopPropagation();
              onSelect(prod);
              close();
            }}
          >
            Seleccionar
          </Button>
        </Box>
      )}
      emptyText="No se encontraron productos."
      onClose={onClose}
    />
  );
};

export default ModalBusquedaProducto;
