import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The data bundle lives in ../data/viewer, which is git-ignored (CLAUDE.md
// rule 3: size, and reproduction runs against the archive itself). Vite
// serves a publicDir at the site root, so the dev server answers
// /documents.json and /pages/*.jpg from it.
//
// A build does NOT copy it (copyPublicDir false), so a local build stays
// 160K rather than 137 MB. The hosted site does carry the bundle:
// .github/workflows/pages.yml downloads release corpus-v1 and copies it
// into dist after the build. Publishing it is settled, by Alex's ruling of
// 2026-09-09: public data, unrestricted at its public source.
export default defineConfig({
  plugins: [react()],
  publicDir: "../data/viewer",
  build: { copyPublicDir: false },
});
