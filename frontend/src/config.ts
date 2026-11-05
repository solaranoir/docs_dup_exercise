/** Solara Radio integration (roadmap DOC-011). Override at build time with VITE_SOLARA_TOOLS_URL. */
export const SOLARA_TOOLS_URL: string =
  import.meta.env.VITE_SOLARA_TOOLS_URL || "https://solararadio.netlify.app/tools";

export const APP_NAME = "Solara Docs";
