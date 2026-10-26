import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

const backend = process.env.COUNTERSIGN_DEV_BACKEND ?? "http://127.0.0.1:8484";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    proxy: {
      "/api": { target: backend, changeOrigin: false },
      "/mcp": { target: backend, changeOrigin: false },
    },
  },
  build: {
    outDir: "dist",
    chunkSizeWarningLimit: 6000,
  },
});
