import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './i18n'
import './theme/omni-tokens.css'
import './platform/native.css'
import './index.css'
import App from './App.tsx'
import { initNativeShell } from './platform/nativeShell'

// Configura el shell nativo (Capacitor/Electron); no-op en web.
void initNativeShell()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
