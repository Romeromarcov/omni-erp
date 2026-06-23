import React from 'react';
import { useQuery } from '@tanstack/react-query';
import { Paper, Table, TableBody, TableCell, TableHead, TableRow, Typography } from '@mui/material';
import { PageContainer, PageHeader } from '../../components/ui';
import { reportesInventarioService } from '../../services/inventarioService';
import { inventarioKeys } from '../../lib/queryKeys';

const ValoracionPage: React.FC = () => {
  const { data: filas = [], isLoading } = useQuery({
    queryKey: inventarioKeys.valoracion(),
    queryFn: () => reportesInventarioService.valoracion(),
  });

  return (
    <PageContainer>
      <PageHeader title="Valoración de inventario" subtitle="Valor de existencias por producto y almacén (FIFO / Promedio)." />
      <Paper sx={{ p: 2 }}>
        {isLoading ? (
          <Typography color="text.secondary">Cargando…</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Producto</TableCell>
                <TableCell>Almacén</TableCell>
                <TableCell>Método</TableCell>
                <TableCell align="right">Cantidad</TableCell>
                <TableCell align="right">Costo prom.</TableCell>
                <TableCell align="right">Valor total</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filas.length === 0 && (
                <TableRow>
                  <TableCell colSpan={6}>
                    <Typography color="text.secondary">Sin existencias valoradas.</Typography>
                  </TableCell>
                </TableRow>
              )}
              {filas.map((f) => (
                <TableRow key={`${f.producto_id}-${f.almacen_id}`}>
                  <TableCell>{f.producto}</TableCell>
                  <TableCell>{f.almacen}</TableCell>
                  <TableCell>{f.metodo}</TableCell>
                  <TableCell align="right">{f.cantidad}</TableCell>
                  <TableCell align="right">{f.costo_promedio}</TableCell>
                  <TableCell align="right">{f.valor_total}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </Paper>
    </PageContainer>
  );
};

export default ValoracionPage;
