import { defineConfig } from "vite";

// Relative base so the same build works at https://<user>.github.io/<repo>/ and locally.
export default defineConfig({
  base: "./",
  worker: { format: "es" },
  build: { target: "es2022", assetsInlineLimit: 0 }, // fonts stay files: the CSP has no data: in font-src
});
