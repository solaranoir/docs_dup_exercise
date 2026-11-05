import { useEffect } from "react";
import { APP_NAME } from "./config";

/** Sets the browser tab title to "<page> · Solara Docs", or just "Solara Docs". */
export function useDocumentTitle(page?: string): void {
  useEffect(() => {
    const trimmed = page?.trim();
    document.title = trimmed ? `${trimmed} · ${APP_NAME}` : APP_NAME;
  }, [page]);
}
