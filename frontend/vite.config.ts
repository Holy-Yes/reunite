import { cpSync, existsSync } from "node:fs";
import { resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";
import react from "@vitejs/plugin-react";

const api = process.env.API_URL ?? "http://127.0.0.1:8010";
const cesiumBuild = resolve("node_modules/cesium/Build/Cesium");
const cesiumDirs = ["Assets", "ThirdParty", "Workers"];

/**
 * Cesium needs its workers and image assets served as plain files. Cesium's JS is bundled normally
 * (so it lives in the lazy /campus chunk and never touches the landing page); only these static
 * folders are served in dev and copied to dist/cesium on build.
 */
function cesiumAssets(): Plugin {
  return {
    name: "cesium-assets",
    configureServer(server) {
      server.middlewares.use("/cesium", (req, res, next) => {
        const file = resolve(cesiumBuild, "." + decodeURIComponent((req.url ?? "/").split("?")[0]));
        if (!file.startsWith(cesiumBuild) || !existsSync(file)) return next();
        import("node:fs").then(({ createReadStream, statSync }) => {
          if (!statSync(file).isFile()) return next();
          if (file.endsWith(".json")) res.setHeader("Content-Type", "application/json");
          if (file.endsWith(".js")) res.setHeader("Content-Type", "text/javascript");
          createReadStream(file).pipe(res);
        });
      });
    },
    closeBundle() {
      for (const d of cesiumDirs) cpSync(resolve(cesiumBuild, d), resolve("dist/cesium", d), { recursive: true });
    },
  };
}

export default defineConfig({
  plugins: [react(), cesiumAssets()],
  define: { CESIUM_BASE_URL: JSON.stringify("/cesium") },
  server: { proxy: { "/api": api, "/media": api, "/health": api } },
});
