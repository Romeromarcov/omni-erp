import { useEffect, useRef, useState } from 'react';
import { Alert, Chip, Collapse } from '@mui/material';
import CloudOffIcon from '@mui/icons-material/CloudOff';
import CloudDoneIcon from '@mui/icons-material/CloudDone';
import { useMutationState } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useOnlineStatus } from '../../hooks/useOnlineStatus';

/** Tiempo que el aviso "conexión restablecida" permanece visible (ms). */
export const RESTORED_BANNER_MS = 4000;

/**
 * Banner global de estado de conexión (offline Nivel 1, ADR-001):
 *  - Sin red: banner warning con badge "datos sin actualizar" (lo que se ve
 *    viene del caché de TanStack/Workbox) y contador de mutaciones en pausa
 *    (`isPaused`, networkMode 'online') que se reanudarán solas.
 *  - Al volver la red: aviso breve de sincronización y desaparece.
 */
export default function OfflineBanner() {
  const { t } = useTranslation();
  const isOnline = useOnlineStatus();

  // Mutaciones pausadas por falta de red (networkMode 'online' → isPaused).
  const pausedCount = useMutationState({
    filters: { status: 'pending' },
    select: (mutation) => mutation.state.isPaused,
  }).filter(Boolean).length;

  // Mostrar brevemente "conexión restablecida" tras una caída.
  const [showRestored, setShowRestored] = useState(false);
  const wasOffline = useRef(false);
  useEffect(() => {
    if (!isOnline) {
      wasOffline.current = true;
      setShowRestored(false);
      return;
    }
    if (wasOffline.current) {
      wasOffline.current = false;
      setShowRestored(true);
      const timer = setTimeout(() => setShowRestored(false), RESTORED_BANNER_MS);
      return () => clearTimeout(timer);
    }
  }, [isOnline]);

  return (
    <>
      <Collapse in={!isOnline} unmountOnExit>
        <Alert
          severity="warning"
          icon={<CloudOffIcon fontSize="inherit" />}
          sx={{ borderRadius: 0 }}
          action={<Chip size="small" color="warning" variant="outlined" label={t('offline.stale')} />}
        >
          {t('offline.banner')}
          {pausedCount > 0 && ` — ${t('offline.pending', { count: pausedCount })}`}
        </Alert>
      </Collapse>
      <Collapse in={isOnline && showRestored} unmountOnExit>
        <Alert severity="success" icon={<CloudDoneIcon fontSize="inherit" />} sx={{ borderRadius: 0 }}>
          {t('offline.restored')}
        </Alert>
      </Collapse>
    </>
  );
}
