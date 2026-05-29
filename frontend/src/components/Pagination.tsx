import { Box, Pagination as MuiPagination, Typography } from '@mui/material';

interface PaginationProps {
  page: number;
  count: number;
  pageSize?: number;
  onChange: (page: number) => void;
}

export default function Pagination({ page, count, pageSize = 20, onChange }: PaginationProps) {
  const totalPages = Math.max(1, Math.ceil(count / pageSize));
  if (totalPages <= 1) return null;
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: 2, mt: 2, flexWrap: 'wrap' }}>
      <MuiPagination
        count={totalPages}
        page={page}
        onChange={(_, p) => onChange(p)}
        color="primary"
        shape="rounded"
      />
      <Typography variant="caption" color="text.secondary">
        {count.toLocaleString()} registros · pág {page}/{totalPages}
      </Typography>
    </Box>
  );
}
