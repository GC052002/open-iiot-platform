/// <reference types="vitest/config" />
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Backend de desarrollo (FastAPI/uvicorn). Se puede sobrescribir con VITE_BACKEND.
const BACKEND = process.env.VITE_BACKEND ?? "http://localhost:8000";

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Proxy en dev: el frontend habla contra el backend real sin CORS ni hosts
    // hardcodeados. En producción el bundle se sirve desde el propio backend.
    proxy: {
      "/ws": { target: BACKEND, changeOrigin: true, ws: true },
      "/login": { target: BACKEND, changeOrigin: true },
      "/projects": { target: BACKEND, changeOrigin: true },
      "/tags": { target: BACKEND, changeOrigin: true },
      "/history": { target: BACKEND, changeOrigin: true },
      "/alarms": { target: BACKEND, changeOrigin: true },
      "/audit": { target: BACKEND, changeOrigin: true },
      "/health": { target: BACKEND, changeOrigin: true },
      "/metrics": { target: BACKEND, changeOrigin: true },
    },
  },
  test: {
    environment: "jsdom",
    globals: true,
    include: ["src/**/*.{test,spec}.{ts,tsx}"],
  },
});
