import { useSyncExternalStore } from "react";

/** Hash routes (#/ and #/doc/:id) need no server-side SPA fallback on the static host. */
export type Route = { name: "list" } | { name: "doc"; id: string };

export function parseRoute(hash: string): Route {
  const match = /^#\/doc\/([\w-]+)$/.exec(hash);
  return match?.[1] ? { name: "doc", id: match[1] } : { name: "list" };
}

const subscribe = (cb: () => void) => {
  window.addEventListener("hashchange", cb);
  return () => window.removeEventListener("hashchange", cb);
};

export function useRoute(): Route {
  const hash = useSyncExternalStore(subscribe, () => window.location.hash);
  return parseRoute(hash);
}

/** Set by the editor while it has unsaved edits, so in-app navigation can ask first. */
export const navigationGuard = { dirty: false };

export function navigate(hash: string): void {
  if (navigationGuard.dirty && !window.confirm("You have unsaved changes. Leave without saving?")) {
    return;
  }
  navigationGuard.dirty = false;
  window.location.hash = hash;
}
