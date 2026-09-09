import { readFileSync } from "node:fs";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The social preview image, emitted at a fixed unhashed name because the
// og:image meta tag in index.html names it absolutely and a hashed filename
// would change under it every build. It cannot live in a public/ directory:
// publicDir is pointed at the data bundle below, and copyPublicDir is off,
// so a public/ here would be ignored twice over. Emitting it costs no new
// dependency and works for a local build and the deployed one alike.
function emitOgPreview() {
  return {
    name: "emit-og-preview",
    generateBundle() {
      this.emitFile({
        type: "asset",
        fileName: "og-preview.png",
        source: readFileSync(
          new URL("./static/og-preview.png", import.meta.url),
        ),
      });
    },
  };
}

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
  plugins: [react(), emitOgPreview()],
  publicDir: "../data/viewer",
  build: { copyPublicDir: false },
});
