import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In Docker Compose dev, set to http://backend:8000 so the Vite container reaches the API.
// Local `npm run dev` keeps the default (127.0.0.1).
const apiTarget = process.env.VITE_DEV_API_TARGET ?? "http://127.0.0.1:8000";
const wsTarget = apiTarget.replace(/^http/, "ws");

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    // Windows bind mounts don't forward file-change events into Docker, so the
    // dev server silently serves stale code without polling.
    watch: { usePolling: true, interval: 300 },
    proxy: {
      "/api": { target: apiTarget, changeOrigin: true },
      "/health": { target: apiTarget, changeOrigin: true },
      "/docs": { target: apiTarget, changeOrigin: true },
      "/openapi.json": { target: apiTarget, changeOrigin: true },
      "/ws": { target: wsTarget, ws: true, changeOrigin: true },
    },
  },
});
