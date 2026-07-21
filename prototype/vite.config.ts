import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Prototype-only Vite config. No production tuning.
// `preview.allowedHosts: true` disables host-header rejection so the
// Emergent preview URL can serve the built dist. This is a prototype
// posture only; production Sprint 1 will be a proper CRA build.
export default defineConfig({
  plugins: [react()],
  server:  { port: 3000, host: '0.0.0.0' },
  preview: { port: 3000, host: '0.0.0.0', allowedHosts: true },
});
