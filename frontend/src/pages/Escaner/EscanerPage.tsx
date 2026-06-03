import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import {
  Box,
  Button,
  Card,
  Chip,
  CircularProgress,
  Divider,
  InputBase,
  Stack,
  ToggleButton,
  ToggleButtonGroup,
  Typography,
} from '@mui/material';
import QrCodeScannerOutlined from '@mui/icons-material/QrCodeScannerOutlined';
import QrCode2Outlined from '@mui/icons-material/QrCode2Outlined';
import ContactlessOutlined from '@mui/icons-material/ContactlessOutlined';
import SearchOutlined from '@mui/icons-material/SearchOutlined';
import CheckCircleOutlined from '@mui/icons-material/CheckCircleOutlined';
import Inventory2Outlined from '@mui/icons-material/Inventory2Outlined';
import ReceiptLongOutlined from '@mui/icons-material/ReceiptLongOutlined';
import RequestQuoteOutlined from '@mui/icons-material/RequestQuoteOutlined';
import AddOutlined from '@mui/icons-material/AddOutlined';
import ArrowForwardOutlined from '@mui/icons-material/ArrowForwardOutlined';
import PageContainer from '../../components/ui/PageContainer';
import PageHeader from '../../components/ui/PageHeader';
import {
  RECENT_SCANS,
  SCAN_MODES,
  resolveScan,
  type ScanMode,
  type ScanResult,
} from '../../services/scannerService';
import './EscanerPage.css';

const MODE_ICON: Record<ScanMode, React.ReactNode> = {
  barcode: <QrCodeScannerOutlined fontSize="small" />,
  qr: <QrCode2Outlined fontSize="small" />,
  nfc: <ContactlessOutlined fontSize="small" />,
};

const ENTITY_ICON: Record<ScanResult['entity'], React.ReactNode> = {
  producto: <Inventory2Outlined fontSize="small" />,
  documento: <ReceiptLongOutlined fontSize="small" />,
  cliente: <RequestQuoteOutlined fontSize="small" />,
};

const ENTITY_COLOR: Record<ScanResult['entity'], string> = {
  producto: '#2e7d32',
  documento: '#0288d1',
  cliente: '#ed6c02',
};

const MODE_HINT: Record<ScanMode, string> = {
  barcode: 'Encuadra el código de barras dentro del marco',
  qr: 'Apunta la cámara al código QR',
  nfc: 'Acerca el dispositivo a la etiqueta NFC',
};

/** Retícula animada del visor según el modo activo. */
function Reticle({ mode }: { mode: ScanMode }) {
  if (mode === 'nfc') {
    return (
      <div className="omni-reticle nfc">
        <div className="waves">
          <b />
          <b />
          <b />
        </div>
        <div className="nicon">
          <ContactlessOutlined sx={{ color: '#fff', fontSize: 30 }} />
        </div>
      </div>
    );
  }
  return (
    <div className={`omni-reticle ${mode}`}>
      <span className="corner tl" />
      <span className="corner tr" />
      <span className="corner bl" />
      <span className="corner br" />
      {mode === 'barcode' && <span className="bars" />}
      <span className="scanline" />
    </div>
  );
}

export default function EscanerPage() {
  const navigate = useNavigate();
  const [mode, setMode] = useState<ScanMode>('barcode');
  const [code, setCode] = useState('');
  const [result, setResult] = useState<ScanResult | null>(null);
  const [scanning, setScanning] = useState(false);

  const changeMode = (next: ScanMode | null) => {
    if (!next) return;
    setMode(next);
    setResult(null);
    setCode(next === 'barcode' ? '7591234008821' : '');
  };

  const doScan = async () => {
    setScanning(true);
    try {
      const r = await resolveScan(mode, code);
      setResult(r);
    } finally {
      setScanning(false);
    }
  };

  const runAction = () => {
    if (!result) return;
    if (result.entity === 'documento') navigate('/ventas/facturas-fiscales');
    else if (result.entity === 'cliente') navigate('/cobranza/dashboard');
    else navigate('/inventario/stock');
  };

  return (
    <PageContainer>
      <PageHeader title="Escáner" subtitle="Lector de códigos de barras, QR y etiquetas NFC" />

      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', md: '1.3fr 1fr' },
          gap: 2,
        }}
      >
        {/* Visor */}
        <Box className="omni-scan-view">
          <Box sx={{ p: 2, position: 'relative', zIndex: 2 }}>
            <ToggleButtonGroup
              exclusive
              value={mode}
              onChange={(_, v) => changeMode(v)}
              size="small"
              sx={{
                gap: 1,
                '& .MuiToggleButton-root': {
                  borderRadius: 999,
                  border: 'none',
                  color: 'rgba(255,255,255,0.7)',
                  bgcolor: 'rgba(255,255,255,0.10)',
                  px: 1.75,
                  py: 0.75,
                  gap: 0.75,
                  textTransform: 'none',
                  fontWeight: 600,
                },
                '& .MuiToggleButton-root.Mui-selected': {
                  color: '#fff',
                  background: 'linear-gradient(135deg,#1976d2 0%,#42a5f5 100%)',
                  boxShadow: '0 8px 20px rgba(25,118,210,0.30)',
                  '&:hover': { background: 'linear-gradient(135deg,#1976d2 0%,#42a5f5 100%)' },
                },
              }}
            >
              {SCAN_MODES.map((m) => (
                <ToggleButton key={m.id} value={m.id}>
                  {MODE_ICON[m.id]}
                  {m.label}
                </ToggleButton>
              ))}
            </ToggleButtonGroup>
          </Box>
          <div className="omni-scan-stage">
            <Reticle mode={mode} />
          </div>
          <Typography
            sx={{
              position: 'relative',
              zIndex: 2,
              textAlign: 'center',
              color: 'rgba(255,255,255,0.7)',
              fontSize: 13,
              fontWeight: 500,
              px: 4,
              pb: 3,
            }}
          >
            {MODE_HINT[mode]}
          </Typography>
        </Box>

        {/* Lector manual + resultado */}
        <Card sx={{ p: 2 }}>
          <Typography variant="subtitle1">Lector manual</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
            Escanee con la pistola lectora o ingrese el código.
          </Typography>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 1,
              border: '1.5px solid',
              borderColor: 'divider',
              borderRadius: 1.5,
              px: 1.5,
              py: 1,
              mb: 1,
              transition: 'border-color .15s, box-shadow .15s',
              '&:focus-within': {
                borderColor: 'primary.main',
                boxShadow: '0 0 0 3px rgba(25,118,210,0.12)',
              },
            }}
          >
            <SearchOutlined fontSize="small" sx={{ color: 'text.secondary' }} />
            <InputBase
              value={code}
              onChange={(e) => setCode(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && doScan()}
              placeholder="Código…"
              sx={{ flex: 1, fontFamily: 'var(--font-mono, monospace)', fontSize: 14 }}
            />
          </Box>
          <Button
            fullWidth
            variant="contained"
            onClick={doScan}
            disabled={scanning}
            startIcon={scanning ? <CircularProgress size={16} color="inherit" /> : <QrCodeScannerOutlined />}
          >
            Buscar / Escanear
          </Button>

          {result ? (
            <Box sx={{ mt: 2 }}>
              <Divider sx={{ mb: 2 }} />
              <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 1.5 }}>
                <Box
                  sx={{
                    width: 40,
                    height: 40,
                    borderRadius: 1.5,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    bgcolor: ENTITY_COLOR[result.entity],
                    color: '#fff',
                  }}
                >
                  {ENTITY_ICON[result.entity]}
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="subtitle2" noWrap title={result.title}>
                    {result.title}
                  </Typography>
                  <Typography variant="caption" color="text.secondary" noWrap display="block">
                    {result.sub}
                  </Typography>
                </Box>
                <Chip
                  icon={<CheckCircleOutlined />}
                  label="Detectado"
                  color="success"
                  size="small"
                  variant="outlined"
                />
              </Stack>
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1,
                  bgcolor: 'background.default',
                  borderRadius: 1.5,
                  px: 1.5,
                  py: 1,
                  mb: 1.5,
                  fontFamily: 'var(--font-mono, monospace)',
                  fontSize: 13,
                  fontWeight: 600,
                }}
              >
                <Typography
                  variant="overline"
                  color="text.secondary"
                  sx={{ lineHeight: 1, letterSpacing: '0.05em' }}
                >
                  {result.kind}
                </Typography>
                <Box sx={{ ml: 'auto' }}>{result.code}</Box>
              </Box>
              {result.rows.map(([k, v]) => (
                <Stack
                  key={k}
                  direction="row"
                  justifyContent="space-between"
                  sx={{ py: 0.75, borderTop: '1px solid', borderColor: 'divider' }}
                >
                  <Typography variant="body2" color="text.secondary">
                    {k}
                  </Typography>
                  <Typography variant="body2" fontWeight={700} sx={{ fontVariantNumeric: 'tabular-nums' }}>
                    {v}
                  </Typography>
                </Stack>
              ))}
              <Button fullWidth variant="contained" sx={{ mt: 1.5 }} startIcon={<AddOutlined />} onClick={runAction}>
                {result.action}
              </Button>
            </Box>
          ) : (
            <Box sx={{ mt: 2 }}>
              <Typography variant="overline" color="text.secondary">
                Escaneos recientes
              </Typography>
              {RECENT_SCANS.map((r) => (
                <Stack
                  key={r.code}
                  direction="row"
                  alignItems="center"
                  spacing={1.5}
                  sx={{ py: 1.25, borderTop: '1px solid', borderColor: 'divider' }}
                >
                  <Box
                    sx={{
                      width: 32,
                      height: 32,
                      borderRadius: 1,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      bgcolor: 'background.default',
                      color: 'text.secondary',
                    }}
                  >
                    {ENTITY_ICON[r.entity]}
                  </Box>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="body2" fontWeight={600} noWrap>
                      {r.title}
                    </Typography>
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ fontFamily: 'var(--font-mono, monospace)' }}
                    >
                      {r.code}
                    </Typography>
                  </Box>
                  <ArrowForwardOutlined fontSize="small" sx={{ color: 'grey.400' }} />
                </Stack>
              ))}
            </Box>
          )}
        </Card>
      </Box>
    </PageContainer>
  );
}
