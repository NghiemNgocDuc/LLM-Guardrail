import React from "react";
import { createRoot } from "react-dom/client";
import App from "../frontend.jsx";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
