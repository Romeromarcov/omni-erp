import React from 'react';
import { Button } from './Button';
import { Dialog, DialogTitle, DialogContent, DialogActions, TextField, List, ListItem, ListItemButton, Typography, Box } from '@mui/material';
import './ModalBusqueda.css';

interface ModalBusquedaProps<T> {
  open: boolean;
  title: string;
  inputPlaceholder?: string;
  inputValue: string;
  onInputChange: (value: string) => void;
  items: T[];
  renderItem: (item: T, onSelect: () => void) => React.ReactNode;
  emptyText?: string;
  onClose: () => void;
  onEnterKey?: () => void;
}

export function ModalBusqueda<T>({
  open,
  title,
  inputPlaceholder = '',
  inputValue,
  onInputChange,
  items,
  renderItem,
  emptyText = 'No se encontraron resultados.',
  onClose,
  onEnterKey,
}: ModalBusquedaProps<T>) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Typography variant="h6" component="h2">
          {title}
        </Typography>
      </DialogTitle>
      <DialogContent>
        <Box sx={{ mb: 2 }}>
          <TextField
            fullWidth
            placeholder={inputPlaceholder}
            value={inputValue}
            onChange={e => onInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && onEnterKey) {
                e.preventDefault();
                onEnterKey();
              }
            }}
            variant="outlined"
            size="small"
          />
        </Box>
        <Box sx={{ maxHeight: 300, overflowY: 'auto' }}>
          {items.length > 0 ? (
            <List>
              {items.map((item, index) => (
                <ListItem key={index} disablePadding>
                  <ListItemButton onClick={() => onClose()}>
                    {renderItem(item, () => onClose())}
                  </ListItemButton>
                </ListItem>
              ))}
            </List>
          ) : (
            inputValue && (
              <Box sx={{ textAlign: 'center', py: 4 }}>
                <Typography variant="body2" color="text.secondary">
                  {emptyText}
                </Typography>
              </Box>
            )
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button type="button" variant="secondary" onClick={onClose}>
          Cerrar
        </Button>
      </DialogActions>
    </Dialog>
  );
}
export default ModalBusqueda;
