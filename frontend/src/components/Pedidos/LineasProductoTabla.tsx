import { useRef, useState } from 'react';
import {
  Box,
  Button,
  Checkbox,
  Drawer,
  Popover,
  Stack,
  Switch,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  useMediaQuery,
  useTheme,
} from '@mui/material';
import ViewWeekOutlined from '@mui/icons-material/ViewWeekOutlined';
import { useColumnVisibility, type ColumnDef } from '../../hooks/useColumnVisibility';

interface LineasProductoTablaProps<T> {
  rows: T[];
  columns: ColumnDef<T>[];
  /** Clave de persistencia de la configuración de columnas (p. ej. el tipo de documento). */
  storageKey: string;
  title?: string;
  getRowKey?: (row: T, index: number) => React.Key;
}

/**
 * Tabla de líneas de producto en modo lectura con selector de columnas
 * configurables al estilo Odoo. La selección se recuerda entre sesiones.
 * Responsive: tabla en escritorio, tarjetas con hoja de "Campos" en móvil.
 */
export default function LineasProductoTabla<T>({
  rows,
  columns,
  storageKey,
  title = 'Líneas de producto',
  getRowKey = (_r, i) => i,
}: LineasProductoTablaProps<T>) {
  const theme = useTheme();
  const isMobile = useMediaQuery(theme.breakpoints.down('md'));
  const { isVisible, toggle } = useColumnVisibility<T>(`lineas_cols_${storageKey}`, columns);
  const [open, setOpen] = useState(false);
  const anchorRef = useRef<HTMLButtonElement>(null);

  const visibleColumns = columns.filter((c) => isVisible(c.key));

  const configButton = (
    <Button
      ref={anchorRef}
      onClick={() => setOpen(true)}
      size="small"
      variant="outlined"
      color="inherit"
      startIcon={<ViewWeekOutlined />}
      sx={{ color: 'text.secondary' }}
    >
      {isMobile ? 'Campos' : 'Columnas'}
    </Button>
  );

  const configRows = (
    <>
      <Typography variant="overline" color="text.secondary" sx={{ px: isMobile ? 2 : 1, display: 'block' }}>
        Columnas opcionales
      </Typography>
      {columns.map((col) => (
        <Box
          key={col.key}
          onClick={() => !col.always && toggle(col.key)}
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            px: isMobile ? 2 : 1,
            py: isMobile ? 1 : 0.5,
            borderRadius: 1,
            cursor: col.always ? 'default' : 'pointer',
            opacity: col.always ? 0.6 : 1,
            '&:hover': { bgcolor: col.always ? 'transparent' : 'action.hover' },
          }}
        >
          {isMobile ? (
            <>
              <Typography variant="body2" sx={{ flex: 1 }}>
                {col.label}
              </Typography>
              {col.always ? (
                <Typography variant="caption" color="text.disabled" sx={{ textTransform: 'uppercase' }}>
                  Fijo
                </Typography>
              ) : (
                <Switch
                  size="small"
                  edge="end"
                  checked={isVisible(col.key)}
                  onChange={() => toggle(col.key)}
                />
              )}
            </>
          ) : (
            <>
              <Checkbox
                size="small"
                checked={isVisible(col.key)}
                disabled={col.always}
                sx={{ p: 0.25 }}
              />
              <Typography variant="body2" sx={{ flex: 1 }}>
                {col.label}
              </Typography>
              {col.always && (
                <Typography variant="caption" color="text.disabled" sx={{ textTransform: 'uppercase' }}>
                  Fijo
                </Typography>
              )}
            </>
          )}
        </Box>
      ))}
    </>
  );

  return (
    <Box>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
        <Typography variant="subtitle1">{title}</Typography>
        {configButton}
      </Box>

      {isMobile ? (
        <Stack spacing={1.5}>
          {rows.map((row, i) => {
            const fixed = visibleColumns.filter((c) => c.always);
            const meta = visibleColumns.filter((c) => !c.always);
            return (
              <Box
                key={getRowKey(row, i)}
                sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, p: 2, bgcolor: 'background.paper' }}
              >
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 1 }}>
                  {fixed[0] && (
                    <Typography variant="subtitle2" fontWeight={700} sx={{ flex: 1 }}>
                      {fixed[0].render(row, i)}
                    </Typography>
                  )}
                  {fixed[1] && (
                    <Typography variant="subtitle2" fontWeight={700} sx={{ fontVariantNumeric: 'tabular-nums' }}>
                      {fixed[1].render(row, i)}
                    </Typography>
                  )}
                </Box>
                {meta.length > 0 && (
                  <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1, mt: 1 }}>
                    {meta.map((c) => (
                      <Typography key={c.key} variant="caption" color="text.secondary">
                        {c.label}: <strong style={{ color: theme.palette.text.primary }}>{c.render(row, i)}</strong>
                      </Typography>
                    ))}
                  </Box>
                )}
              </Box>
            );
          })}
        </Stack>
      ) : (
        <TableContainer>
          <Table size="small">
            <TableHead>
              <TableRow>
                {visibleColumns.map((c) => (
                  <TableCell key={c.key} align={c.align ?? 'left'}>
                    {c.label}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {rows.map((row, i) => (
                <TableRow key={getRowKey(row, i)}>
                  {visibleColumns.map((c) => (
                    <TableCell key={c.key} align={c.align ?? 'left'}>
                      {c.render(row, i)}
                    </TableCell>
                  ))}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Configurador: popover en escritorio, hoja inferior en móvil */}
      {isMobile ? (
        <Drawer
          anchor="bottom"
          open={open}
          onClose={() => setOpen(false)}
          slotProps={{ paper: { sx: { borderTopLeftRadius: 16, borderTopRightRadius: 16, pb: 2 } } }}
        >
          <Box sx={{ width: 36, height: 4, bgcolor: 'divider', borderRadius: 2, mx: 'auto', mt: 1.5, mb: 1 }} />
          <Box sx={{ py: 1 }}>{configRows}</Box>
          <Box sx={{ px: 2, mt: 1 }}>
            <Button fullWidth variant="contained" onClick={() => setOpen(false)}>
              Listo
            </Button>
          </Box>
        </Drawer>
      ) : (
        <Popover
          open={open}
          anchorEl={anchorRef.current}
          onClose={() => setOpen(false)}
          anchorOrigin={{ vertical: 'bottom', horizontal: 'right' }}
          transformOrigin={{ vertical: 'top', horizontal: 'right' }}
          slotProps={{ paper: { sx: { width: 240, p: 1, mt: 0.5 } } }}
        >
          {configRows}
        </Popover>
      )}
    </Box>
  );
}
