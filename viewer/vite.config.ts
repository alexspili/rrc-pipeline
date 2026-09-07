import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The data bundle lives in ../data/viewer, which is never committed
// (CLAUDE.md rule 3: extracted values and page images carry personal
// information). The dev server serves it at /data; a production build does
// NOT copy it (copyPublicDir false), so dist/ stays personal-data-free and
// the viewer is run against a bundle the operator supplies.
export default defineConfig({
  plugins: [react()],
  publicDir: "../data/viewer",
  build: { copyPublicDir: false },
});
