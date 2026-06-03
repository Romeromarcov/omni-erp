import './components/DashboardCard.css';
import AppRouter from './router';
import { ThemeProvider } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';
import { AuthProvider } from './contexts/AuthContext';
import { FeedbackProvider } from './contexts/FeedbackContext';
import { QueryClientProvider } from '@tanstack/react-query';
import { queryClient } from './lib/queryClient';
import theme from './theme/theme';

function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        <CssBaseline />
        <FeedbackProvider>
          <AuthProvider>
            <AppRouter />
          </AuthProvider>
        </FeedbackProvider>
      </ThemeProvider>
    </QueryClientProvider>
  );
}

export default App;
