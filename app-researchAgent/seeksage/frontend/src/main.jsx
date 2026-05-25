import React from "react";
import ReactDOM from "react-dom/client";
import { BrowserRouter } from "react-router-dom";

import App from "./App";
import "./styles.css";

const inferredBase = window.location.pathname.startsWith("/seeksage") ? "/seeksage" : "/";
const routerBase = import.meta.env.VITE_ROUTER_BASENAME || inferredBase;

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <BrowserRouter basename={routerBase}>
      <App />
    </BrowserRouter>
  </React.StrictMode>
);
