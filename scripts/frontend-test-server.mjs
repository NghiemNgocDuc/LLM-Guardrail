// Exercise the production assets rather than Vite's lazy development compiler.
import { build, preview } from "vite";

const privateMode = process.env.VITE_PRIVATE_MODE === "true";
const outDir = privateMode ? "dist-private" : "dist-test";
const port = privateMode ? 5175 : 5173;

await build({ build: { outDir } });
await preview({
  build: { outDir },
  preview: { host: "127.0.0.1", port, strictPort: true },
});
