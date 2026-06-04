import React, { useState } from 'react';
import {
  Box, TextField, Button, Paper, List, ListItem, ListItemButton,
  Typography, Grid,
} from '@mui/material';
import type { Producto } from '../../services/productosService';
import type { PedidoDetalleForm } from './TablaProductos';

interface FormularioProductoProps {
  productos: Producto[];
  detalleForm: PedidoDetalleForm;
  onChange: (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => void;
  onAdd: (e: React.FormEvent) => void;
  onSelectProducto?: (prod: Producto) => void;
}


const FormularioProducto: React.FC<FormularioProductoProps> = ({ productos, detalleForm, onChange, onAdd, onSelectProducto }) => {
  const [busquedaSku, setBusquedaSku] = useState('');
  const [showSugerenciasSku, setShowSugerenciasSku] = useState(false);
  const [busquedaNombre, setBusquedaNombre] = useState('');
  const [showSugerenciasNombre, setShowSugerenciasNombre] = useState(false);
  const sugerenciasSku = busquedaSku.length > 0
    ? productos.filter(p => (p.sku || '').toLowerCase().includes(busquedaSku.trim().toLowerCase()))
    : [];
  const sugerenciasNombre = busquedaNombre.length > 0
    ? productos.filter(p => p.nombre_producto.toLowerCase().includes(busquedaNombre.trim().toLowerCase()))
    : [];

  // Sincroniza los inputs con el estado global detalleForm
  React.useEffect(() => {
    setBusquedaSku(detalleForm.sku || '');
    setBusquedaNombre(detalleForm.producto || '');
  }, [detalleForm.sku, detalleForm.producto]);

  const handleInputChangeSku = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setBusquedaSku(value);
    setShowSugerenciasSku(true);
    onChange({ ...e, target: { ...e.target, value } });
  };

  const handleInputChangeNombre = (e: React.ChangeEvent<HTMLInputElement>) => {
    const value = e.target.value;
    setBusquedaNombre(value);
    setShowSugerenciasNombre(true);
    onChange({ ...e, target: { ...e.target, value } });
  };

  const handleSelectProducto = (prod: Producto) => {
    setShowSugerenciasSku(false);
    setShowSugerenciasNombre(false);
    if (onSelectProducto) onSelectProducto(prod);
    onChange({ target: { name: 'id_producto', value: prod.id_producto } } as React.ChangeEvent<HTMLInputElement>);
    onChange({ target: { name: 'precio_unitario', value: prod.precio_venta_sugerido ?? '' } } as React.ChangeEvent<HTMLInputElement>);
    onChange({ target: { name: 'sku', value: prod.sku ?? '' } } as React.ChangeEvent<HTMLInputElement>);
    onChange({ target: { name: 'producto', value: prod.nombre_producto } } as React.ChangeEvent<HTMLInputElement>);
  };

  const suggestionPaper = {
    position: 'absolute' as const,
    top: '100%',
    left: 0,
    right: 0,
    zIndex: 10,
    maxHeight: 200,
    overflowY: 'auto' as const,
    mt: 0.5,
    borderRadius: 2,
    boxShadow: 'var(--omni-shadow-card-soft, 0 4px 16px rgba(0,0,0,0.10))',
  };

  return (
    <Box sx={{ mb: 1.5 }}>
      <Grid container spacing={1.5} alignItems="flex-start">
        {/* SKU */}
        <Grid size={{ xs: 12, sm: 6, md: 2 }}>
          <Box sx={{ position: 'relative' }}>
            <TextField
              fullWidth
              size="small"
              label="SKU"
              name="sku"
              value={detalleForm.sku || ''}
              onChange={handleInputChangeSku}
              placeholder="Buscar SKU..."
              autoComplete="off"
              onFocus={() => setShowSugerenciasSku(true)}
              onBlur={() => setTimeout(() => setShowSugerenciasSku(false), 150)}
            />
            {showSugerenciasSku && sugerenciasSku.length > 0 && (
              <Paper sx={suggestionPaper}>
                <List dense disablePadding>
                  {sugerenciasSku.map(prod => (
                    <ListItem key={prod.id_producto} disablePadding>
                      <ListItemButton onMouseDown={() => handleSelectProducto(prod)} sx={{ py: 0.75 }}>
                        <Typography variant="body2">
                          <strong>{prod.sku}</strong> — {prod.nombre_producto}
                        </Typography>
                      </ListItemButton>
                    </ListItem>
                  ))}
                </List>
              </Paper>
            )}
          </Box>
        </Grid>

        {/* Nombre */}
        <Grid size={{ xs: 12, sm: 6, md: 3 }}>
          <Box sx={{ position: 'relative' }}>
            <TextField
              fullWidth
              size="small"
              label="Producto"
              name="producto"
              value={detalleForm.producto || ''}
              onChange={handleInputChangeNombre}
              placeholder="Buscar producto..."
              autoComplete="off"
              onFocus={() => setShowSugerenciasNombre(true)}
              onBlur={() => setTimeout(() => setShowSugerenciasNombre(false), 150)}
            />
            {showSugerenciasNombre && sugerenciasNombre.length > 0 && (
              <Paper sx={suggestionPaper}>
                <List dense disablePadding>
                  {sugerenciasNombre.map(prod => (
                    <ListItem key={prod.id_producto} disablePadding>
                      <ListItemButton onMouseDown={() => handleSelectProducto(prod)} sx={{ py: 0.75 }}>
                        <Typography variant="body2">
                          {prod.nombre_producto}{prod.sku ? ` (${prod.sku})` : ''}
                        </Typography>
                      </ListItemButton>
                    </ListItem>
                  ))}
                </List>
              </Paper>
            )}
          </Box>
        </Grid>

        {/* Cantidad */}
        <Grid size={{ xs: 6, sm: 4, md: 1.5 }}>
          <TextField
            fullWidth
            size="small"
            label="Cantidad"
            name="cantidad"
            type="number"
            inputProps={{ min: 0.01, step: 0.01 }}
            value={detalleForm.cantidad}
            onChange={onChange}
            onKeyDown={(e) => {
              if (e.key === 'Enter') { e.preventDefault(); onAdd(e as unknown as React.FormEvent); }
            }}
          />
        </Grid>

        {/* Precio */}
        <Grid size={{ xs: 6, sm: 4, md: 1.5 }}>
          <TextField
            fullWidth
            size="small"
            label="Precio"
            name="precio_unitario"
            type="number"
            inputProps={{ min: 0.01, step: 0.01 }}
            value={detalleForm.precio_unitario}
            onChange={onChange}
          />
        </Grid>

        {/* Descuento */}
        <Grid size={{ xs: 6, sm: 4, md: 1.5 }}>
          <TextField
            fullWidth
            size="small"
            label="% Desc."
            name="descuento_porcentaje"
            type="number"
            inputProps={{ min: 0, max: 100, step: 0.01 }}
            value={detalleForm.descuento_porcentaje || ''}
            onChange={onChange}
          />
        </Grid>

        {/* Comentarios */}
        <Grid size={{ xs: 12, sm: 8, md: 2.5 }}>
          <TextField
            fullWidth
            size="small"
            label="Comentarios (opcional)"
            name="comentarios"
            multiline
            maxRows={3}
            value={detalleForm.comentarios || ''}
            onChange={onChange}
            inputProps={{ maxLength: 500 }}
          />
        </Grid>

        {/* Agregar */}
        <Grid size={{ xs: 6, sm: 4, md: 'auto' }}>
          <Button type="button" variant="contained" onClick={onAdd} fullWidth>
            Agregar
          </Button>
        </Grid>
      </Grid>
    </Box>
  );
};

export default FormularioProducto;
