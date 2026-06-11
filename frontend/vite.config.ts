import { defineConfig, type ViteDevServer } from "vite";
import react from "@vitejs/plugin-react";

const backendTarget = "http://127.0.0.1:18083";
const backendProxy = {
  target: backendTarget,
  changeOrigin: true
};

const cleanConsolePaths = new Set([
  "/",
  "/single",
  "/backtests/portfolio",
  "/backtests/single-stock",
  "/daily",
  "/trading/daily-plan",
  "/paper",
  "/trading/paper",
  "/paper/templates",
  "/portfolio/paper-templates",
  "/stock-pools",
  "/portfolio/stock-pools",
  "/admin",
  "/system/admin",
  "/users",
  "/system/users",
  "/sector",
  "/research/sectors",
  "/market-data",
  "/market-data/factors",
  "/market-data/stocks",
  "/system/health"
]);

function cleanConsoleRouteFallback() {
  return {
    name: "clean-console-route-fallback",
    configureServer(server: ViteDevServer) {
      server.middlewares.use((req, _res, next) => {
        const path = (req.url || "").split("?", 1)[0].replace(/\/$/, "") || "/";
        if (cleanConsolePaths.has(path)) {
          req.url = "/static/console/";
        }
        next();
      });
    }
  };
}

export default defineConfig({
  plugins: [react(), cleanConsoleRouteFallback()],
  base: "/static/console/",
  build: {
    outDir: "../static/console",
    emptyOutDir: true
  },
  server: {
    port: 5173,
    strictPort: false,
    proxy: {
      "/api": backendProxy,
      "/health": backendProxy,
      "/login": backendProxy,
      "/register": backendProxy,
      "/static/style.css": backendProxy,
      "/static/assets": backendProxy,
      "/static/vendor": backendProxy
    }
  }
});
