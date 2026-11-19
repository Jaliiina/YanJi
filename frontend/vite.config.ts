import tailwindcss from "@tailwindcss/vite";
import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";
export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (
            id.includes("node_modules/echarts/") ||
            id.includes("node_modules/zrender/")
          )
            return "charts";
          if (id.includes("node_modules/react")) return "react";
        },
      },
    },
  },
  server: { proxy: { "/api": "http://127.0.0.1:8810" } },
});
