import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), "VITE_");
  const privateMode = (process.env.VITE_PRIVATE_MODE ?? env.VITE_PRIVATE_MODE) === "true";
  return {
    plugins: [react(), ...(privateMode ? [{
      name: "private-local-fonts",
      enforce: "pre",
      transform(code, id) {
        if (id.split("?")[0].endsWith("/src/styles/global.css")) {
          return { code: code.replace(/^@import.*fonts\.googleapis\.com.*;[\r\n]*/gm, ""), map: null };
        }
      },
    }] : [])],
    optimizeDeps: { entries: ["index.html"] },
    cacheDir: privateMode ? "node_modules/.vite-private" : "node_modules/.vite",
    server: { host: "0.0.0.0", port: 5173 },
    build: { outDir: "dist" },
  };
});
