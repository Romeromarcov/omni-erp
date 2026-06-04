import React, { useState } from 'react';
import ModalBusqueda from '../ModalBusqueda';
import type { Cliente } from '../../services/clientesService';
import { buscarClientes } from '../../services/clientesService';
import { Box, Button, Typography } from '@mui/material';

interface ModalBusquedaClienteProps {
  open: boolean;
  idEmpresa: string;
  onSelect: (cli: Cliente) => void;
  onClose: () => void;
}

const ModalBusquedaCliente: React.FC<ModalBusquedaClienteProps> = ({ open, idEmpresa, onSelect, onClose }) => {
  const [busqueda, setBusqueda] = useState('');
  const [resultados, setResultados] = useState<Cliente[]>([]);

  const handleInputChange = async (value: string) => {
    setBusqueda(value);
    if (value.trim()) {
      const results = await buscarClientes(value, idEmpresa);
      setResultados(Array.isArray(results) ? results : []);
    } else {
      setResultados([]);
    }
  };

  return (
    <ModalBusqueda
      open={open}
      title="Buscar cliente existente"
      inputPlaceholder="Buscar por nombre, RIF..."
      inputValue={busqueda}
      onInputChange={handleInputChange}
      items={resultados}
      renderItem={(cli, close) => (
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', width: '100%', gap: 1 }}>
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="body2" fontWeight={600} noWrap>
              {cli.razon_social}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              RIF: {cli.rif} | Tel: {cli.telefono}
            </Typography>
          </Box>
          <Button
            type="button"
            variant="contained"
            size="small"
            sx={{ flexShrink: 0 }}
            onClick={(e) => {
              e.stopPropagation();
              onSelect(cli);
              close();
            }}
          >
            Seleccionar
          </Button>
        </Box>
      )}
      emptyText="No se encontraron clientes."
      onClose={onClose}
    />
  );
};

export default ModalBusquedaCliente;
