import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const legacyTarget = "http://127.0.0.1:18083";
const legacyProxy = {
  target: legacyTarget,
  changeOrigin: true
};

export default defineConfig({
  plugins: [react()],
  base: "/static/console/",
  build: {
    outDir: "../static/console",
    emptyOutDir: true
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      "/__legacy": {
        ...legacyProxy,
        rewrite: (path) => path.replace(/^\/__legacy\/index/, "/")
      },
      "/api": legacyProxy,
      "/health": legacyProxy,
      "/single": legacyProxy,
      "/daily": legacyProxy,
      "/paper": legacyProxy,
      "/stock-pools": legacyProxy,
      "/admin": legacyProxy,
      "/users": legacyProxy,
      "/sector": legacyProxy,
      "/login": legacyProxy,
      "/register": legacyProxy,
      "/static/style.css": legacyProxy,
      "/static/assets": legacyProxy,
      "/static/app.js": legacyProxy,
      "/static/auth.js": legacyProxy,
      "/static/daily.js": legacyProxy,
      "/static/paper.js": legacyProxy,
      "/static/paper_templates.js": legacyProxy,
      "/static/sector.js": legacyProxy,
      "/static/single.js": legacyProxy,
      "/static/stock_pools.js": legacyProxy,
      "/static/admin.js": legacyProxy,
      "/static/users.js": legacyProxy,
      "/static/vendor": legacyProxy
    }
  }
});
