import { defineConfig } from "vitest/config";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
  },
  build: {
    // Keep the lazy-loaded MapLibre engine separate from the application shell.
    chunkSizeWarningLimit: 1100,
  },
  server: {
    port: 5173,
  },
});
