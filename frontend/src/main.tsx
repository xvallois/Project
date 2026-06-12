import React from "react";
import { createRoot } from "react-dom/client";
import "dockview/dist/styles/dockview.css";
import "./styles/app.css";
import App from "./App";

createRoot(document.getElementById("root")!).render(
  <React.StrictMode><App /></React.StrictMode>);
