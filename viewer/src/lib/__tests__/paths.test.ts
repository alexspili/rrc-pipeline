import { describe, expect, it } from "vitest";
import { assetUrl } from "../paths";

/** The viewer is served two ways: from the dev server at the domain root,
 * and from GitHub Pages under a project path. Every bundle request has to
 * be correct in both, so the join is a function and not a template string
 * scattered over three call sites. */
describe("assetUrl joins a site base to a bundle path", () => {
  it("joins the dev server base", () => {
    expect(assetUrl("/", "pages/1493399-0-12.jpg")).toBe(
      "/pages/1493399-0-12.jpg",
    );
  });

  it("joins a project-site base", () => {
    expect(assetUrl("/rrc-pipeline/", "documents.json")).toBe(
      "/rrc-pipeline/documents.json",
    );
  });

  // Vite documents BASE_URL as always ending in a slash. This does not rest
  // on that being true of every version.
  it("gives the same answer for a base with no trailing slash", () => {
    expect(assetUrl("/rrc-pipeline", "documents.json")).toBe(
      assetUrl("/rrc-pipeline/", "documents.json"),
    );
  });

  // loadAll defaulted to "" and built `${base}/documents.json`. Keeping that
  // exact output is what leaves `make demo` working as the README documents.
  it("keeps the empty base rooted, as loadAll's default produced before", () => {
    expect(assetUrl("", "documents.json")).toBe("/documents.json");
  });

  it("never emits a double slash", () => {
    for (const base of ["", "/", "/rrc-pipeline", "/rrc-pipeline/"])
      for (const path of ["documents.json", "/documents.json", "pages/a.jpg"])
        expect(assetUrl(base, path)).not.toContain("//");
  });

  it("joins once when the path carries a leading slash", () => {
    expect(assetUrl("/rrc-pipeline/", "/pages/a.jpg")).toBe(
      "/rrc-pipeline/pages/a.jpg",
    );
  });
});
