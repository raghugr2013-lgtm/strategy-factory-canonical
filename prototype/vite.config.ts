import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

// Prototype-only Vite config. No production tuning.
export default defineConfig({
  plugins: [react()],
  server: { port: 3000, host: '0.0.0.0' },
});
