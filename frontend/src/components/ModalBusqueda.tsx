import React from 'react';
import { Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField, List, ListItem, ListItemButton, Typography, Box } from '@mui/material';

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
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      slotProps={{
        paper: {
          sx: {
            borderRadius: 'var(--omni-radius-card-xl, 20px)',
            boxShadow: 'var(--omni-shadow-card-soft, 0 4px 24px rgba(0,0,0,0.10))',
            overflow: 'hidden',
            width: { xs: '95vw', md: '80%' },
            maxWidth: 700,
          },
        },
      }}
    >
      <DialogTitle sx={{ pb: 1 }}>
        <Typography variant="h6" component="h2" sx={{ fontWeight: 700, fontSize: 16, letterSpacing: '-0.2px' }}>
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
            autoFocus
          />
        </Box>
        <Box sx={{ maxHeight: 340, overflowY: 'auto' }}>
          {items.length > 0 ? (
            <List disablePadding>
              {items.map((item, index) => (
                <ListItem key={index} disablePadding>
                  <ListItemButton
                    onClick={() => onClose()}
                    sx={{
                      borderRadius: 1,
                      mx: 0.5,
                      '&:hover': { bgcolor: 'var(--omni-tint-primary, rgba(99,102,241,0.06))' },
                    }}
                  >
                    {renderItem(item, () => onClose())}
                  </ListItemButton>
                </ListItem>
              ))}
            </List>
          ) : (
            inputValue && (
              <Box sx={{ textAlign: 'center', py: 5 }}>
                <Typography variant="body2" color="text.secondary">
                  {emptyText}
                </Typography>
              </Box>
            )
          )}
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button type="button" variant="outlined" onClick={onClose}>
          Cerrar
        </Button>
      </DialogActions>
    </Dialog>
  );
}
export default ModalBusqueda;
