import { createRoot } from "react-dom/client";
import { PlayerProvider } from "./Player";
import { AppShell } from "./AppShell";
import "./styles.css";
import { registerCache } from "./prefetch";
registerCache();
createRoot(document.getElementById("root")!).render(
  <PlayerProvider>
    <AppShell />
  </PlayerProvider>,
);
