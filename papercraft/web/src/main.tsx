import React from "react";
import ReactDOM from "react-dom/client";
import "katex/dist/katex.min.css";
import "./styles.css";
import { App } from "./App";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);

window.__PAPERCRAFT_BOOTED__ = true;
document.getElementById("boot-fallback")?.setAttribute("hidden", "");
