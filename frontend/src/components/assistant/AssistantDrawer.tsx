import { useEffect, useRef, useState } from 'react';
import {
  Avatar,
  Box,
  Drawer,
  IconButton,
  InputBase,
  Paper,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material';
import CloseIcon from '@mui/icons-material/Close';
import SendIcon from '@mui/icons-material/Send';
import StopCircleOutlined from '@mui/icons-material/StopCircleOutlined';
import DeleteOutline from '@mui/icons-material/DeleteOutline';
import AutoAwesomeOutlined from '@mui/icons-material/AutoAwesomeOutlined';
import { useAssistant } from '../../contexts/AssistantContext';
import Markdown from './Markdown';

const SUGERENCIAS = [
  '¿Cómo registro una nueva venta?',
  '¿Qué es la tasa BCV y dónde la configuro?',
  'Explícame el flujo de cobranza (CxC)',
  '¿Cómo hago un ajuste de inventario?',
];

export default function AssistantDrawer() {
  const { open, setOpen, chat } = useAssistant();
  const { messages, streaming, error, send, stop, reset } = chat;
  const [input, setInput] = useState('');
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' });
  }, [messages]);

  const handleSend = () => {
    if (!input.trim() || streaming) return;
    send(input);
    setInput('');
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={() => setOpen(false)}
      PaperProps={{ sx: { width: { xs: '100%', sm: 420 }, display: 'flex', flexDirection: 'column' } }}
    >
      {/* Header */}
      <Box
        sx={{
          px: 2,
          py: 1.5,
          display: 'flex',
          alignItems: 'center',
          gap: 1,
          borderBottom: '1px solid',
          borderColor: 'divider',
        }}
      >
        <Avatar sx={{ bgcolor: 'primary.main', width: 32, height: 32 }}>
          <AutoAwesomeOutlined fontSize="small" />
        </Avatar>
        <Box flexGrow={1}>
          <Typography variant="subtitle1" lineHeight={1.1}>Asistente Omni</Typography>
          <Typography variant="caption" color="text.secondary">IA conversacional del ERP</Typography>
        </Box>
        <Tooltip title="Nueva conversación">
          <span>
            <IconButton size="small" onClick={reset} disabled={streaming || messages.length === 0}>
              <DeleteOutline fontSize="small" />
            </IconButton>
          </span>
        </Tooltip>
        <IconButton size="small" onClick={() => setOpen(false)}>
          <CloseIcon fontSize="small" />
        </IconButton>
      </Box>

      {/* Messages */}
      <Box ref={scrollRef} sx={{ flexGrow: 1, overflowY: 'auto', px: 2, py: 2, bgcolor: 'grey.50' }}>
        {messages.length === 0 ? (
          <Stack spacing={2} alignItems="center" justifyContent="center" height="100%" textAlign="center">
            <Avatar sx={{ bgcolor: 'primary.main', width: 56, height: 56 }}>
              <AutoAwesomeOutlined />
            </Avatar>
            <Box>
              <Typography variant="h6">¿En qué te ayudo?</Typography>
              <Typography variant="body2" color="text.secondary">
                Pregúntame sobre cualquier módulo del ERP.
              </Typography>
            </Box>
            <Stack spacing={1} width="100%">
              {SUGERENCIAS.map((s) => (
                <Paper
                  key={s}
                  variant="outlined"
                  onClick={() => send(s)}
                  sx={{
                    p: 1.25,
                    cursor: 'pointer',
                    textAlign: 'left',
                    '&:hover': { bgcolor: 'action.hover', borderColor: 'primary.main' },
                  }}
                >
                  <Typography variant="body2">{s}</Typography>
                </Paper>
              ))}
            </Stack>
          </Stack>
        ) : (
          <Stack spacing={1.5}>
            {messages.map((m, i) => (
              <Box
                key={i}
                sx={{
                  display: 'flex',
                  justifyContent: m.role === 'user' ? 'flex-end' : 'flex-start',
                }}
              >
                <Paper
                  elevation={0}
                  sx={{
                    px: 1.5,
                    py: 1,
                    maxWidth: '85%',
                    bgcolor: m.role === 'user' ? 'primary.main' : 'background.paper',
                    color: m.role === 'user' ? 'primary.contrastText' : 'text.primary',
                    border: m.role === 'user' ? 'none' : '1px solid',
                    borderColor: 'divider',
                    borderRadius: 2,
                    wordBreak: 'break-word',
                  }}
                >
                  {m.role === 'user' ? (
                    <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
                      {m.content}
                    </Typography>
                  ) : m.content ? (
                    <Markdown>{m.content}</Markdown>
                  ) : (
                    <Typography variant="body2">
                      {streaming && i === messages.length - 1 ? '▋' : ''}
                    </Typography>
                  )}
                </Paper>
              </Box>
            ))}
            {error && (
              <Typography variant="caption" color="error">
                {error}
              </Typography>
            )}
          </Stack>
        )}
      </Box>

      {/* Input */}
      <Box sx={{ p: 1.5, borderTop: '1px solid', borderColor: 'divider' }}>
        <Paper
          variant="outlined"
          sx={{ display: 'flex', alignItems: 'flex-end', gap: 0.5, px: 1, py: 0.5, borderRadius: 3 }}
        >
          <InputBase
            multiline
            maxRows={5}
            fullWidth
            placeholder="Escribe tu mensaje…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            sx={{ px: 1, py: 0.5 }}
          />
          {streaming ? (
            <Tooltip title="Detener">
              <IconButton color="error" onClick={stop}>
                <StopCircleOutlined />
              </IconButton>
            </Tooltip>
          ) : (
            <Tooltip title="Enviar">
              <span>
                <IconButton color="primary" onClick={handleSend} disabled={!input.trim()}>
                  <SendIcon />
                </IconButton>
              </span>
            </Tooltip>
          )}
        </Paper>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5, textAlign: 'center' }}>
          Enter para enviar · Shift+Enter para nueva línea
        </Typography>
      </Box>
    </Drawer>
  );
}
