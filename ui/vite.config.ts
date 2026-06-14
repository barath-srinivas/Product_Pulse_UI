import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

/**
 * Vite configuration for Product Review Pulse UI.
 *
 * Local dev:  npm run dev  →  http://localhost:5173
 *             API calls proxy to http://127.0.0.1:8000 (pulse-api on Railway locally)
 *
 * Vercel:     set VITE_API_URL to your Railway API URL in Project → Settings → Environment Variables
 */
export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "");
  const apiTarget = env.VITE_API_PROXY_TARGET || "http://127.0.0.1:8000";

  return {
    plugins: [react()],
    server: {
      port: 5173,
      proxy: {
        "/api": {
          target: apiTarget,
          changeOrigin: true,
        },
        "/health": {
          target: apiTarget,
          changeOrigin: true,
        },
      },
    },
    build: {
      outDir: "dist",
      sourcemap: true,
    },
  };
});
