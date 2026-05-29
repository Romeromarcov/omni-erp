import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';
import {
  Box,
  Link,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
} from '@mui/material';

/** Renderiza Markdown (GFM) con componentes MUI, para las respuestas del asistente. */
export default function Markdown({ children }: { children: string }) {
  return (
    <Box sx={{ '& > :first-of-type': { mt: 0 }, '& > :last-child': { mb: 0 } }}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          p: ({ children }) => (
            <Typography variant="body2" sx={{ my: 0.75, lineHeight: 1.6 }}>
              {children}
            </Typography>
          ),
          h1: ({ children }) => (
            <Typography variant="h6" sx={{ mt: 1.5, mb: 0.5, fontWeight: 700 }}>{children}</Typography>
          ),
          h2: ({ children }) => (
            <Typography variant="subtitle1" sx={{ mt: 1.5, mb: 0.5, fontWeight: 700 }}>{children}</Typography>
          ),
          h3: ({ children }) => (
            <Typography variant="subtitle2" sx={{ mt: 1.25, mb: 0.5, fontWeight: 700 }}>{children}</Typography>
          ),
          ul: ({ children }) => (
            <Box component="ul" sx={{ my: 0.5, pl: 2.5, '& li': { mb: 0.25 } }}>{children}</Box>
          ),
          ol: ({ children }) => (
            <Box component="ol" sx={{ my: 0.5, pl: 2.5, '& li': { mb: 0.25 } }}>{children}</Box>
          ),
          li: ({ children }) => (
            <Typography component="li" variant="body2" sx={{ lineHeight: 1.6 }}>{children}</Typography>
          ),
          a: ({ children, href }) => (
            <Link href={href} target="_blank" rel="noopener noreferrer" underline="hover">{children}</Link>
          ),
          strong: ({ children }) => <Box component="strong" sx={{ fontWeight: 700 }}>{children}</Box>,
          code: ({ children, ...props }) => {
            const inline = !String(props.className || '').includes('language-');
            if (inline) {
              return (
                <Box
                  component="code"
                  sx={{
                    px: 0.5,
                    py: 0.1,
                    borderRadius: 0.5,
                    bgcolor: 'action.hover',
                    fontFamily: 'monospace',
                    fontSize: '0.85em',
                  }}
                >
                  {children}
                </Box>
              );
            }
            return (
              <Box
                component="pre"
                sx={{
                  my: 1,
                  p: 1.25,
                  borderRadius: 1,
                  bgcolor: '#1e1e1e',
                  color: '#d4d4d4',
                  overflowX: 'auto',
                  fontFamily: 'monospace',
                  fontSize: '0.8rem',
                }}
              >
                <code>{children}</code>
              </Box>
            );
          },
          table: ({ children }) => (
            <TableContainer sx={{ my: 1 }}>
              <Table size="small">{children}</Table>
            </TableContainer>
          ),
          thead: ({ children }) => <TableHead>{children}</TableHead>,
          tbody: ({ children }) => <TableBody>{children}</TableBody>,
          tr: ({ children }) => <TableRow>{children}</TableRow>,
          th: ({ children }) => <TableCell sx={{ fontWeight: 700 }}>{children}</TableCell>,
          td: ({ children }) => <TableCell>{children}</TableCell>,
        }}
      >
        {children}
      </ReactMarkdown>
    </Box>
  );
}
