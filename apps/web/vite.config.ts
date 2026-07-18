import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
  },
  build: {
    // MapLibre is lazy-loaded as an isolated engine chunk; the app shell stays below 210 kB.
    chunkSizeWarningLimit: 1100,
  },
  server: {
    port: 5173,
  },
});
