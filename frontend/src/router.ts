import { useSyncExternalStore } from "react";

/**
 * Path routes (DOC-013): `/` and `/doc/:id`, via the History API. The static host rewrites
 * unknown paths to index.html (render.yaml); Vite's dev server does the same.
 */
export type Route = { name: "list" } | { name: "doc"; id: string } | { name: "not-found" };

export const paths = {
  list: "/",
  doc: (id: string) => `/doc/${encodeURIComponent(id)}`,
};

export function parseRoute(pathname: string): Route {
  if (pathname === "/" || pathname === "") return { name: "list" };
  const match = /^\/doc\/([\w-]+)\/?$/.exec(pathname);
  return match?.[1] ? { name: "doc", id: match[1] } : { name: "not-found" };
}

/**
 * Links from before DOC-013 used `#/` and `#/doc/:id`. Rewrite them in place (no reload, no
 * extra history entry) so old bookmarks and shared links keep working. Other hashes, such as
 * the skip link's `#main`, are left alone.
 */
export function migrateLegacyHash(): void {
  const { hash, search } = window.location;
  if (!hash.startsWith("#/")) return;
  window.history.replaceState(window.history.state, "", hash.slice(1) + search);
}

const NAVIGATE_EVENT = "solara:navigate";

const subscribe = (cb: () => void) => {
  window.addEventListener("popstate", cb);
  window.addEventListener(NAVIGATE_EVENT, cb);
  return () => {
    window.removeEventListener("popstate", cb);
    window.removeEventListener(NAVIGATE_EVENT, cb);
  };
};

export function useRoute(): Route {
  const pathname = useSyncExternalStore(subscribe, () => window.location.pathname);
  return parseRoute(pathname);
}

/** Set by the editor while it has unsaved edits, so in-app navigation can ask first. */
export const navigationGuard = { dirty: false };

/** In-app navigation. Returns false if the user chose to stay on a page with unsaved edits. */
export function navigate(path: string, { replace = false } = {}): boolean {
  if (navigationGuard.dirty && !window.confirm("You have unsaved changes. Leave without saving?")) {
    return false;
  }
  navigationGuard.dirty = false;
  if (path !== window.location.pathname + window.location.search) {
    if (replace) window.history.replaceState(null, "", path);
    else window.history.pushState(null, "", path);
  }
  window.dispatchEvent(new Event(NAVIGATE_EVENT));
  return true;
}
