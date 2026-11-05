import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./App";
import { migrateLegacyHash } from "./router";
import "./styles.css";

migrateLegacyHash(); // old #/doc/:id links → /doc/:id, before the first render

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>,
);
