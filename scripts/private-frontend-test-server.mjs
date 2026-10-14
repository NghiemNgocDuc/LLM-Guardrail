// Exercise the production assets rather than Vite's lazy development compiler.
import { build, preview } from "vite";

await build({ build: { outDir: "dist-private" } });
await preview({
  build: { outDir: "dist-private" },
  preview: { host: "127.0.0.1", port: 5175, strictPort: true },
});
