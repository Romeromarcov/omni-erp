import { Box, Button, Card, CardContent, Typography, CircularProgress, Alert, Paper } from '@mui/material';
import { SmartToy as RobotIcon, Refresh as RefreshIcon } from '@mui/icons-material';
import { useAgenteStream } from '../../hooks/useCxC';
import { PageContainer, PageHeader } from '../../components/ui';

export default function AgenteCobranzaPage() {
  const { streaming, output, error, iniciar, limpiar } = useAgenteStream();

  return (
    <PageContainer>
      <PageHeader
        title="Agente de Cobranza IA"
        subtitle="Análisis inteligente de cartera vencida y recomendaciones personalizadas"
      />

      <Card sx={{ mb: 2 }}>
        <CardContent>
          <Typography variant="body2" color="text.secondary" mb={2}>
            El agente analiza la cartera vencida, prioriza clientes por score y genera recomendaciones de cobranza personalizadas.
          </Typography>
          <Box display="flex" gap={1} flexWrap="wrap">
            <Button
              variant="contained"
              onClick={() => iniciar('analizar_cartera')}
              disabled={streaming}
              startIcon={streaming ? <CircularProgress size={16} /> : undefined}
            >
              {streaming ? 'Analizando...' : 'Analizar Cartera Completa'}
            </Button>
            <Button
              variant="outlined"
              onClick={limpiar}
              disabled={streaming}
              startIcon={<RefreshIcon />}
            >
              Limpiar
            </Button>
          </Box>
        </CardContent>
      </Card>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {(output || streaming) && (
        <Paper
          sx={{
            p: 2,
            minHeight: 200,
            maxHeight: 500,
            overflow: 'auto',
            bgcolor: '#1e1e1e',
            color: '#d4d4d4',
            fontFamily: 'monospace',
            fontSize: '0.875rem',
            whiteSpace: 'pre-wrap',
            wordBreak: 'break-word',
          }}
        >
          {output}
          {streaming && <span style={{ opacity: 0.7 }}>▋</span>}
        </Paper>
      )}

      {!output && !streaming && (
        <Paper sx={{ p: 4, textAlign: 'center', color: 'text.secondary' }}>
          <RobotIcon sx={{ fontSize: 48, opacity: 0.3, mb: 1 }} />
          <Typography>Presiona "Analizar Cartera Completa" para iniciar el análisis</Typography>
        </Paper>
      )}
    </PageContainer>
  );
}
