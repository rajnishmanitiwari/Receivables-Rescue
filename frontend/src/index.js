import React from "react";
import { createRoot } from "react-dom/client";

// Fonts are bundled rather than pulled from Google, so the app renders correctly
// on corporate and school networks that block third-party font hosts, and loads
// without a second round-trip on slow connections.
import "@fontsource/source-serif-4/400.css";
import "@fontsource/source-serif-4/600.css";
import "@fontsource/ibm-plex-sans/400.css";
import "@fontsource/ibm-plex-sans/500.css";
import "@fontsource/ibm-plex-sans/600.css";

import App from "./App";
import "./styles.css";

createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>
);
