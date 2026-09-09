/** Where the bundle is, relative to where the viewer itself is served.
 *
 * The viewer is served two ways and both have to work. The dev server and
 * `make demo` serve it at the root of localhost, where /documents.json is
 * right. GitHub Pages serves a project site under /rrc-pipeline/, where the
 * same request is a 404. The build is told which one it is compiling for
 * (vite --base), and every bundle request goes through the join below.
 *
 * assetUrl is pure and takes the base as an argument, so it is tier-1
 * testable with no build environment. SITE_BASE and pageUrl are the thin
 * binding to the compiled-in value and are not tier-1 tested. */

/** Join a site base to a bundle-relative path with exactly one slash. */
export function assetUrl(base: string, path: string): string {
  return `${base.replace(/\/+$/, "")}/${path.replace(/^\/+/, "")}`;
}

/** The base this build was compiled for: "/" in dev, "/rrc-pipeline/" on
 * Pages. Vite substitutes it at build time. */
export const SITE_BASE: string = import.meta.env.BASE_URL;

/** Page image URL for a page key, in whichever way this build is served. */
export function pageUrl(key: string): string {
  return assetUrl(SITE_BASE, `pages/${key}.jpg`);
}
