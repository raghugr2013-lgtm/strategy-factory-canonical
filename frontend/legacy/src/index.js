import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import "@/index.css";
import App from "@/App";
import { bootstrapA11yPatcher } from "@/a11y/formNamePatcher";
import { installAuthFetchInterceptor } from "@/services/auth";

// RC1 · AX-1 / AX-2 — runtime accessible-name patcher for form controls.
// See /app/frontend/src/a11y/formNamePatcher.js for the resolution order.
bootstrapA11yPatcher();

// RC1 · AUTH-FIX — install global Authorization: Bearer interceptor at boot.
// Resolves the cascading HTTP 401 chips on Ingestion Health, Parity Cert,
// Pipeline Logs, Strategy Ingestion, Auto Data Maintenance, Monitoring &
// Control, Soak/CPU/Cluster, Flags/Realism/Tuning, LLM Live River, and the
// downstream "body stream already read" cosmetic error. See
// /app/memory/AUTHENTICATION_AUDIT.md for the audit trail.
installAuthFetchInterceptor();

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      refetchOnWindowFocus: false,
    },
  },
});

const root = ReactDOM.createRoot(document.getElementById("root"));
root.render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <App />
    </QueryClientProvider>
  </React.StrictMode>,
);
