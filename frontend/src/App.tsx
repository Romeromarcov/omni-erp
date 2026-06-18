import './components/DashboardCard.css';
import AppRouter from './router';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { AuthProvider } from './contexts/AuthContext';
import { FeedbackProvider } from './contexts/FeedbackContext';
import { PersistQueryClientProvider } from '@tanstack/react-query-persist-client';
import { queryClient } from './lib/queryClient';
import { idbPersister } from './lib/idbPersister';
import theme from './theme/theme';

// Offline Nivel 1 "réplica local" (ADR-001): rehidrata el caché de TanStack
// desde IndexedDB al arrancar, de modo que la app abre con datos aunque inicie
// sin red. maxAge 24 h descarta réplicas viejas; buster invalida todo el caché
// persistido cuando cambia la versión del bundle (evita rehidratar formas de
// datos incompatibles tras un deploy).
const persistOptions = {
  persister: idbPersister,
  maxAge: 1000 * 60 * 60 * 24,
  buster: import.meta.env.VITE_APP_VERSION ?? 'dev',
};

function App() {
  return (
    <PersistQueryClientProvider client={queryClient} persistOptions={persistOptions}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <FeedbackProvider>
          <AuthProvider>
            <AppRouter />
          </AuthProvider>
        </FeedbackProvider>
      </ThemeProvider>
    </PersistQueryClientProvider>
  );
}

export default App;
